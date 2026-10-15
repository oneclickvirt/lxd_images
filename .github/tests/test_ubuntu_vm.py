"""Execute the resize hook with consumer disk layouts and failed growpart calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from image_source_compat import UBUNTU_GROW_ROOT, ubuntu_vm_compat


class UbuntuRootGrowthTests(unittest.TestCase):
    def execute(self, root='/dev/vda2', parent='vda', part='2', status=0,
                message='CHANGED: partition=2', kind='part', fstype='ext4'):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            commands = folder / 'commands.jsonl'
            stub = folder / 'fixture'
            stub.write_text('#!' + sys.executable + '\n' + r'''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COMMANDS'], 'a') as stream:
    stream.write(json.dumps([name, *args]) + '\n')
if name == 'findmnt':
    print(os.environ['ROOT'] if 'SOURCE' in args else os.environ['FSTYPE'])
elif name == 'readlink':
    print(os.environ['ROOT'])
elif name == 'lsblk':
    print(os.environ['KIND'] if 'TYPE' in args else os.environ['PARENT'])
elif name == 'cat':
    assert args == ['/sys/class/block/' + Path(os.environ['ROOT']).name + '/partition']
    print(os.environ['PART'])
elif name == 'growpart':
    print(os.environ['MESSAGE'])
    sys.exit(int(os.environ['STATUS']))
''')
            stub.chmod(0o755)
            for command in ('findmnt', 'readlink', 'lsblk', 'cat', 'growpart', 'resize2fs'):
                (folder / command).symlink_to(stub)
            environment = dict(os.environ, PATH=str(folder) + os.pathsep + os.environ['PATH'],
                               ROOT=root, PARENT=parent, PART=part, STATUS=str(status),
                               MESSAGE=message, KIND=kind, FSTYPE=fstype, COMMANDS=str(commands))
            result = subprocess.run(['sh', '-c', UBUNTU_GROW_ROOT], env=environment,
                                    capture_output=True, text=True, timeout=10)
            return result, [json.loads(line) for line in commands.read_text().splitlines()]

    def test_detects_virtio_scsi_and_nvme_root_partitions(self):
        for root, parent, part in (('/dev/vda2', 'vda', '2'), ('/dev/sda3', 'sda', '3'),
                                   ('/dev/nvme0n1p12', 'nvme0n1', '12')):
            with self.subTest(root=root):
                result, calls = self.execute(root, parent, part)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(['growpart', '/dev/' + parent, part], calls)
                self.assertEqual(calls[-1], ['resize2fs', root])

    def test_reboot_nochange_still_checks_and_resizes_the_filesystem(self):
        result, calls = self.execute(status=1, message='NOCHANGE: partition 2 is size 20969439')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1], ['resize2fs', '/dev/vda2'])

    def test_growpart_error_does_not_continue_to_resize(self):
        for status, message in ((1, 'FAILED: cannot read disk'), (2, 'NOCHANGE: misleading failure')):
            result, calls = self.execute(status=status, message=message)
            self.assertEqual(result.returncode, status)
            self.assertFalse(any(call[0] == 'resize2fs' for call in calls))

    def test_rejects_nonpartition_and_nonext4_roots(self):
        for options in ({'kind': 'lvm'}, {'fstype': 'xfs'}, {'part': ''},
                        {'parent': '../sda'}, {'part': '0'}):
            result, calls = self.execute(**options)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(call[0] in ('growpart', 'resize2fs') for call in calls))

    def test_upstream_growth_hook_retains_its_variant_scope_and_is_idempotent(self):
        for runtime in ('incus', 'lxd'):
            growth = {'trigger': 'post-files', 'types': ['vm'], 'variants': ['default'],
                      'action': 'cat << EOF > /etc/systemd/system/' + runtime + '-growpart.service\n'
                                'ExecStartPre=-/usr/bin/growpart /dev/sda 2\nEOF\n'}
            document = {'actions': [growth]}
            ubuntu_vm_compat(document)
            first = json.dumps(document, sort_keys=True)
            ubuntu_vm_compat(document)
            self.assertEqual(first, json.dumps(document, sort_keys=True))
            self.assertEqual(growth['variants'], ['default'])
            self.assertIn(UBUNTU_GROW_ROOT, growth['action'])
            self.assertIn('/etc/systemd/system/' + runtime + '-growpart.service', growth['action'])
            self.assertNotIn('/dev/sda', growth['action'])
            subprocess.run(['sh', '-n'], input=growth['action'], text=True, check=True)
            network = document['actions'][-1]
            self.assertEqual(network['types'], ['vm'])
            self.assertEqual(network['releases'], ['noble', 'resolute'])
            self.assertNotIn('variants', network)
            self.assertIn('systemctl enable systemd-networkd.service', network['action'])


if __name__ == '__main__':
    unittest.main()
