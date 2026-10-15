import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import os
import sys
import subprocess
from unittest import mock
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

    def test_runtime_console_reads_a_tty_and_never_inherits_tokens(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / 'console.py'
            fixture.write_text('import os,sys\n'
                               'assert os.isatty(0)\n'
                               'assert "GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ\n'
                               'print("Kernel fixture: missing virtio driver",flush=True)\n')
            with mock.patch.dict(os.environ, GH_TOKEN='private-a', GITHUB_TOKEN='private-b'):
                output = diagnostics.capture_console([sys.executable, str(fixture)])
            self.assertIn('Kernel fixture: missing virtio driver', output)
            self.assertNotIn('AssertionError', output)


class NativeVMOfflineTests(unittest.TestCase):
    def test_running_vm_disk_is_never_opened(self):
        state = subprocess.CompletedProcess([], 0, '{"status_code":103}', '')
        with mock.patch.object(diagnostics.subprocess, 'run', return_value=state), \
                mock.patch.object(Path, 'is_file') as inspect_disk:
            with self.assertRaisesRegex(RuntimeError, 'must be stopped'):
                diagnostics.stopped_disk(Path('/unavailable'), 'test-012345abcdef', 'incus')
        inspect_disk.assert_not_called()

    def test_stopped_vm_uses_its_disposable_storage_volume(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            disk = base / 'storage-pools/default/virtual-machines/test-012345abcdef/root.img'
            disk.parent.mkdir(parents=True)
            disk.write_bytes(b'disposable disk')
            state = subprocess.CompletedProcess([], 0, '{"status_code":102}', '')
            with mock.patch.dict(os.environ, GH_TOKEN='secret-a', GITHUB_TOKEN='secret-b'), \
                    mock.patch.object(diagnostics.subprocess, 'run', return_value=state) as execute:
                self.assertEqual(diagnostics.stopped_disk(base, 'test-012345abcdef', '/snap/bin/lxc'), disk)
            self.assertNotIn('GH_TOKEN', execute.call_args.kwargs['env'])
            self.assertNotIn('GITHUB_TOKEN', execute.call_args.kwargs['env'])
            self.assertEqual(execute.call_args.kwargs['timeout'], 15)

    def test_missing_stopped_volume_preserves_failure(self):
        state = subprocess.CompletedProcess([], 0, '{"status_code":102}', '')
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(diagnostics.subprocess, 'run', return_value=state):
            with self.assertRaises(FileNotFoundError):
                diagnostics.stopped_disk(Path(temporary), 'test-012345abcdef', 'incus')

    def test_offline_reads_are_bounded_and_exclude_credentials(self):
        output = io.StringIO()
        result = subprocess.CompletedProcess([], 0, 'journal ' + 'x' * 50000, '')
        with mock.patch.dict(os.environ, GH_TOKEN='secret-a', GITHUB_TOKEN='secret-b'), \
                mock.patch.object(diagnostics.subprocess, 'run', return_value=result) as execute, \
                redirect_stdout(output):
            diagnostics.offline_diagnostics(Path('/tmp/disposable/root.img'))
        self.assertLess(len(output.getvalue()), 64200)
        self.assertEqual([call.args[0][0] for call in execute.call_args_list], ['virt-log', 'virt-cat'])
        for call in execute.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 60)
            self.assertEqual(call.kwargs['env']['LIBGUESTFS_BACKEND'], 'direct')
            self.assertNotIn('GH_TOKEN', call.kwargs['env'])
            self.assertNotIn('GITHUB_TOKEN', call.kwargs['env'])

    def test_guestfs_failure_does_not_replace_the_original_image_error(self):
        output = io.StringIO()
        with mock.patch.object(diagnostics.subprocess, 'run', side_effect=OSError('fixture')), redirect_stdout(output):
            diagnostics.offline_diagnostics(Path('/tmp/disposable/root.img'))
        self.assertEqual(output.getvalue().count('unavailable: OSError'), 2)


if __name__ == '__main__':
    unittest.main()
