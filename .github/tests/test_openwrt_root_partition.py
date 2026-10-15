"""Execute the upstream boot hook with valid, missing and malformed root metadata."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from image_source_compat import openwrt_vm_root


class OpenWrtRootPartitionTests(unittest.TestCase):
    def test_boot_hooks_retain_partition_uuid_and_reject_incomplete_metadata(self):
        document = yaml.safe_load((ROOT / 'images_yaml/openwrt.yaml').read_text())
        original = copy.deepcopy(document)
        openwrt_vm_root(document)
        openwrt_vm_root(document)
        self.assertEqual(document, original)
        hooks = [a for a in document['actions'] if 'hosted-openwrt-root-partuuid' in a['action']]
        self.assertEqual(len(hooks), 2)
        for hook in hooks:
            with self.subTest(architectures=hook['architectures']), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                config = folder / 'grub.cfg'
                self.assertIn(hook['types'], [['vm']])
                action = hook['action']
                target = next(line.removeprefix('target=') for line in action.splitlines() if line.startswith('target='))
                # GNU and BSD sed accept an attached backup suffix.
                action = action.replace(target, str(config)).replace("sed -i ", "sed -i.bak ")
                rootvar = 'LXD_IMAGEBUILDER_ROOT_PARTUUID' if 'LXD_IMAGEBUILDER_ROOT_PARTUUID' in action else 'DISTROBUILDER_ROOT_PARTUUID'
                for identifier in ('', 'UUID=1234', 'PARTUUID=wrong/value', 'PARTUUID='):
                    baseline = 'linux /boot/Image root=PARTUUID=vendor-id console=ttyAMA0 rootwait\n'
                    config.write_text(baseline)
                    environment = dict(os.environ, **{rootvar: identifier})
                    result = subprocess.run(['sh', '-c', action], env=environment, capture_output=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0, identifier)
                    self.assertEqual(config.read_text(), baseline)
                environment = dict(os.environ, **{rootvar: 'PARTUUID=12345678-1234-5678-1234-567812345678'})
                for _ in range(2):
                    subprocess.run(['sh', '-c', action], env=environment, capture_output=True, check=True, timeout=5)
                self.assertIn('root=PARTUUID=12345678-1234-5678-1234-567812345678 console=ttyAMA0 rootwait', config.read_text())
                config.write_text('linux /boot/Image console=ttyAMA0\n')
                result = subprocess.run(['sh', '-c', action], env=environment, capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                config.unlink()
                result = subprocess.run(['sh', '-c', action], env=environment, capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)

    def test_changed_upstream_boot_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            openwrt_vm_root({'actions': []})


if __name__ == '__main__':
    unittest.main()
