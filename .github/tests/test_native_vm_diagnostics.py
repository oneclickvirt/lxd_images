import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
import io

spec = importlib.util.spec_from_file_location('native_vm_diagnostics', Path(__file__).resolve().parents[1] / 'scripts/native_vm_diagnostics.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class NativeVMConsoleTests(unittest.TestCase):
    def test_read_only_monitor_exchanges_work_without_a_guest_agent(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'monitor'
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(1)
            commands = []
            errors = []
            def serve():
                try:
                    with server.accept()[0] as client:
                        client.sendall(b'{"QMP":{}}\n')
                        reader = client.makefile('rb')
                        for answer in ({}, [{'label': 'console', 'filename': 'ringbuf'}], 'Kernel panic: fixture boot failure'):
                            request = json.loads(reader.readline())
                            commands.append(request)
                            client.sendall(b'{"event":"fixture"}\n')
                            payload = (json.dumps({'id': request['id'], 'return': answer}) + '\n').encode()
                            client.sendall(payload[:5])
                            client.sendall(payload[5:])
                except Exception as error:
                    errors.append(error)
                finally:
                    server.close()
            thread = threading.Thread(target=serve)
            thread.start()
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    diagnostics.console(path)
            finally:
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors)
            self.assertEqual([row['execute'] for row in commands], ['qmp_capabilities', 'query-chardev', 'ringbuf-read'])
            self.assertEqual(commands[-1]['arguments'], {'device': 'console', 'size': 65536})
            self.assertIn('Kernel panic: fixture boot failure', output.getvalue())

    def test_absent_monitor_preserves_an_error(self):
        with self.assertRaises(OSError):
            diagnostics.console(Path('/nonexistent-disposable-vm/monitor'))


if __name__ == '__main__':
    unittest.main()
