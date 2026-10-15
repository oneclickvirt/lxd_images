"""Exercise console authentication, result framing and rejection over real sockets."""
import importlib.util
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location('console_runtime', Path(__file__).resolve().parents[1] / 'scripts/hosted_image_test.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
BOOT = '2b175b98-8e84-4f79-b781-25b4f64f0866'


class OpenWrtConsoleTests(unittest.TestCase):
    def exchange(self, reply, timeout=2, reboot=False, script=None):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'console.sock'
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path)); server.listen(1)
            errors = []
            def serve():
                try:
                    with server.accept()[0] as client:
                        client.settimeout(3)
                        reply(client)
                except Exception as error:
                    errors.append(error)
                finally:
                    server.close()
            thread = threading.Thread(target=serve); thread.start()
            try:
                return runtime.openwrt_console_command(path, 'private-fixture-password', runtime.CHECK if script is None else script,
                                                       timeout=timeout, reboot=reboot)
            finally:
                thread.join(4)
                self.assertFalse(thread.is_alive(), 'console fixture exceeded its budget')
                if errors:
                    raise errors[0]

    def read_command(self, client):
        command = b''
        while not command.endswith(b'\r'):
            part = client.recv(4096)
            self.assertTrue(part)
            command += part
        return command

    def command_reply(self, client, status=0, framed=True):
        command = self.read_command(client)
        self.assertNotIn(b'private-fixture-password', command)
        marker = re.search(rb'hosted_console_[0-9a-f]+', command)[0]
        # Echoed shell source is never proof that the guest ran assertions.
        client.sendall(command + b'\r\n')
        if framed:
            client.sendall(b'\r\n' + marker + b'_begin\r\n')
        client.sendall(BOOT.encode() + b'\r\n' + marker + b'_end:' + str(status).encode() + b'\r\nroot@OpenWrt:/# ')

    def root_shell(self, client):
        self.assertEqual(self.read_command(client), b'\r')
        client.sendall(b'\r\nroot@OpenWrt:/# ')

    def test_existing_host_console_needs_no_password_in_shell_commands(self):
        def reply(client):
            self.root_shell(client); self.command_reply(client)
        self.assertEqual(self.exchange(reply), BOOT)

    def test_password_only_follows_complete_split_password_prompt(self):
        def reply(client):
            self.assertEqual(self.read_command(client), b'\r')
            client.sendall(b'\r\nOpenWrt login: ')
            self.assertEqual(self.read_command(client), b'root\r')
            client.sendall(b'\r\nPass'); client.sendall(b'word: ')
            self.assertEqual(self.read_command(client), b'private-fixture-password\r')
            client.sendall(b'\r\nroot@OpenWrt:/# ')
            self.command_reply(client)
        self.assertEqual(self.exchange(reply), BOOT)

    def test_guest_assertion_failure_is_never_success(self):
        def reply(client):
            self.root_shell(client); self.command_reply(client, status=1)
        with self.assertRaisesRegex(RuntimeError, 'guest assertions failed'):
            self.exchange(reply)

    def test_echoed_command_cannot_supply_missing_result_frame(self):
        def reply(client):
            self.root_shell(client); self.command_reply(client, framed=False)
        with self.assertRaisesRegex(RuntimeError, 'framing failed'):
            self.exchange(reply)

    def test_disconnected_console_is_failure(self):
        def reply(client):
            self.assertEqual(self.read_command(client), b'\r')
        with self.assertRaises(ConnectionError):
            self.exchange(reply)

    def test_failed_login_is_bounded_and_does_not_expose_password(self):
        def reply(client):
            self.assertEqual(self.read_command(client), b'\r')
            for _ in range(2):
                client.sendall(b'\r\nOpenWrt login: ')
                self.assertEqual(self.read_command(client), b'root\r')
                client.sendall(b'\r\nPassword: ')
                self.assertEqual(self.read_command(client), b'private-fixture-password\r')
            client.sendall(b'\r\nOpenWrt login: ')
        with self.assertRaisesRegex(RuntimeError, '^OpenWrt consumer console login failed$'):
            self.exchange(reply)

    def test_reboot_uses_the_existing_guest_service(self):
        def reply(client):
            self.root_shell(client)
            command = self.read_command(client)
            self.assertIn(b'test -s /etc/openwrt_release && reboot;', command)
            self.assertNotIn(b'reboot -f', command)
            marker = re.search(rb'hosted_console_[0-9a-f]+', command)[0]
            # The caller must remain attached until execution, not merely
            # accept echoed source as evidence that reboot was requested.
            client.sendall(command + b'\r\n')
            client.settimeout(0.05)
            with self.assertRaises(TimeoutError):
                client.recv(1)
            client.sendall(b'\r\n' + marker + b'_reboot_requested\r\n')
        self.assertEqual(self.exchange(reply, reboot=True), '')

    def test_reboot_command_failure_is_rejected(self):
        def reply(client):
            self.root_shell(client)
            command = self.read_command(client)
            marker = re.search(rb'hosted_console_[0-9a-f]+', command)[0]
            client.sendall(b'\r\n' + marker + b'_reboot_rejected\r\n')
        with self.assertRaisesRegex(RuntimeError, 'rejected the reboot command'):
            self.exchange(reply, reboot=True)

    def test_reboot_requires_execution_acknowledgement_before_disconnect(self):
        def reply(client):
            self.root_shell(client)
            client.sendall(self.read_command(client) + b'\r\n')
        with self.assertRaisesRegex(ConnectionError, 'before reboot acknowledgement'):
            self.exchange(reply, reboot=True)

    def test_missing_prompt_respects_deadline(self):
        def reply(client):
            self.assertEqual(self.read_command(client), b'\r')
            client.sendall(b'Guest still booting\r\n')
            self.assertEqual(client.recv(1), b'')
        with self.assertRaises(TimeoutError):
            self.exchange(reply, timeout=0.1)

    def execute_wire_program(self, client):
        self.root_shell(client)
        command = self.read_command(client).decode()
        self.assertNotIn('base64', command)
        self.assertLess(max(map(len, command.splitlines())), 1000)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            identity = folder / 'openwrt_release'; identity.write_text('fixture identity')
            # Adapt only the two host identity assertions. All transmitted
            # quoting, heredoc parsing, script execution and status framing run
            # through an actual POSIX shell with no base64 in PATH.
            command = command.replace('test "$(id -u)" = 0', 'test "$(id -u)" = ' + str(os.getuid()))
            command = command.replace('test -s /etc/openwrt_release', 'test -s ' + shlex.quote(str(identity)))
            (folder / 'id').symlink_to(shutil.which('id'))
            result = subprocess.run(['/bin/sh'], input=command.replace('\r', '\n'), text=True,
                                    capture_output=True, env={'PATH': str(folder)}, timeout=2)
            self.assertEqual(result.returncode, 0, result.stderr)
            client.sendall(result.stdout.encode())

    def test_real_posix_wire_program_needs_no_guest_decoder(self):
        script = "printf '%s\\n' '" + BOOT + "'\n"
        self.assertEqual(self.exchange(self.execute_wire_program, script=script), BOOT)

    def test_real_shell_preserves_guest_script_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'guest assertions failed'):
            self.exchange(self.execute_wire_program, script='exit 23\n')


if __name__ == '__main__':
    unittest.main()
