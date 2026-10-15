"""Read disposable native VM logs even when its guest agent cannot start."""
import argparse
import json
from pathlib import Path
import re
import socket
import time


def console(sock):
    """Read only QMP diagnostics; never resume, reset or reconfigure a VM."""
    deadline = time.monotonic() + 8
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(2)
        stream.connect(str(sock))
        buffered = b''
        def receive(identifier=None):
            nonlocal buffered
            while time.monotonic() < deadline:
                stream.settimeout(max(0.01, min(2, deadline - time.monotonic())))
                while b'\n' not in buffered:
                    data = stream.recv(8192)
                    if not data:
                        raise ConnectionError('QMP closed before a diagnostic response')
                    buffered += data
                    if len(buffered) > 262144:
                        raise ValueError('QMP diagnostic response exceeds the limit')
                line, buffered = buffered.split(b'\n', 1)
                value = json.loads(line)
                if identifier is None or value.get('id') == identifier:
                    if 'error' in value:
                        raise RuntimeError('QMP diagnostic command unavailable')
                    return value
            raise TimeoutError('QMP diagnostic deadline exceeded')
        receive()
        def command(name, arguments=None):
            request = {'execute': name, 'id': name}
            if arguments is not None:
                request['arguments'] = arguments
            stream.sendall((json.dumps(request) + '\n').encode())
            return receive(name).get('return')
        command('qmp_capabilities')
        devices = command('query-chardev')
        for device in devices:
            if device.get('filename') == 'ringbuf':
                output = command('ringbuf-read', {'device': device['label'], 'size': 65536})
                if isinstance(output, str) and output:
                    print('Native VM serial buffer:\n' + output[-16000:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--runtime', choices=('incus', 'lxd'), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'test-[0-9a-f]{12}', args.name):
        raise ValueError('Only disposable validation instances may be diagnosed')
    base = Path('/var/lib/incus') if args.runtime == 'incus' else Path('/var/snap/lxd/common/lxd')
    logs = Path('/var/log/incus') if args.runtime == 'incus' else base / 'logs'
    for filename in ('qemu.log', 'console.log'):
        path = logs / args.name / filename
        if path.is_file():
            with path.open('rb') as source:
                source.seek(max(0, path.stat().st_size - 12000))
                print(filename + ':\n' + source.read(12000).decode(errors='replace'))
    candidates = [logs / args.name / 'qemu.monitor', base / 'run' / args.name / 'qemu.monitor']
    if args.runtime == 'incus':
        candidates.insert(0, Path('/run/incus') / args.name / 'qemu.monitor')
    for path in candidates:
        if path.is_socket():
            try:
                console(path)
            except (OSError, ValueError, RuntimeError, TimeoutError) as error:
                print('Native VM serial diagnostics unavailable: ' + type(error).__name__)
            return
    print('Native VM monitor unavailable; existing guest acceptance failure is retained')


if __name__ == '__main__':
    main()
