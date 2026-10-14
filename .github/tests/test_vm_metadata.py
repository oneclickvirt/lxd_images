"""Exercise real metadata tarball patching, including template retention."""
import io
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class VMMetadataTests(unittest.TestCase):
    def test_secureboot_property_is_a_single_string_and_templates_survive(self):
        source = (ROOT / 'build_kvm_images.sh').read_text()
        name = 'lxd' if 'patch_lxd_metadata_for_kvm()' in source else 'incus'
        function = re.search(r'^patch_' + name + r'_metadata_for_kvm\(\) \{.*?^\}', source, re.M | re.S).group(0)
        required = re.search(r'^requires_secureboot_disabled\(\) \{.*?^\}', source, re.M | re.S)
        harness = (required.group(0) + '\n' if required else '') + function + '\nrun_funct=alpine\npatch_' + name + '_metadata_for_kvm fixture.zip\n'
        for properties in ['properties:\n  description: fixture\n',
                           'properties:\n  description: fixture\n  requirements.secureboot: true\n',
                           'properties: {}\n', '']:
            with self.subTest(properties=properties), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                path = folder / (name + '.tar.xz')
                value = ('architecture: aarch64\ncreation_date: 1\n' + properties + 'templates:\n  /etc/hosts:\n    template: hosts.tpl\n    when: [create]\n').encode()
                with tarfile.open(path, 'w:xz') as archive:
                    for member, content in [('metadata.yaml', value), ('templates/hosts.tpl', b'fixture-template')]:
                        info = tarfile.TarInfo(member); info.size = len(content); archive.addfile(info, io.BytesIO(content))
                for _ in range(2):
                    subprocess.run(['bash', '-euc', harness], cwd=folder, check=True, capture_output=True, timeout=15)
                    with tarfile.open(path) as archive:
                        metadata = archive.extractfile('metadata.yaml').read().decode()
                        self.assertEqual(archive.extractfile('templates/hosts.tpl').read(), b'fixture-template')
                    parsed = yaml.safe_load(metadata)
                    self.assertEqual(parsed['properties']['requirements.secureboot'], 'false')
                    self.assertIsInstance(parsed['properties']['requirements.secureboot'], str)
                    self.assertEqual(metadata.count('requirements.secureboot:'), 1)
                    self.assertNotIn('requirements', parsed)
                    self.assertEqual(parsed['templates']['/etc/hosts']['template'], 'hosts.tpl')


if __name__ == '__main__':
    unittest.main()
