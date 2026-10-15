from pathlib import Path
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from published_image_suite import matrix


class PublishedSuiteTests(unittest.TestCase):
    def setUp(self):
        self.assets = [{'name': name, 'tag': 'fixture'} for name in (
            'debian_13_trixie_x86_64_default.zip', 'debian_13_trixie_x86_64_cloud.zip',
            'debian_13_trixie_aarch64_default_kvm.zip', 'debian_13_trixie_aarch64_cloud_kvm.zip',
            'fedora_44_44_amd64_default_kvm.zip')]

    def test_vm_smoke_selects_real_default_asset_and_hosted_arm(self):
        result = matrix(self.assets, ROOT.name, 'smoke', 'vm')['include']
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['image'], 'debian_13_trixie_aarch64_default_kvm.zip')
        self.assertEqual(result[0]['runner'], 'ubuntu-24.04-arm')
        self.assertEqual(result[0]['tag'], 'fixture')

    def test_container_smoke_does_not_mix_vm_or_cloud_images(self):
        result = matrix(self.assets, ROOT.name, 'smoke', 'container')['include']
        self.assertEqual([row['image'] for row in result], ['debian_13_trixie_x86_64_default.zip'])

    def test_full_and_exact_asset_checks_keep_cloud_and_other_distributions(self):
        result = matrix(self.assets, ROOT.name, 'full', 'vm')['include']
        self.assertEqual(len(result), 3)
        exact = matrix([self.assets[-1]], ROOT.name, 'full', 'vm')['include']
        self.assertEqual(exact[0]['image'], self.assets[-1]['name'])

    def test_empty_or_invalid_selection_fails_without_a_success_marker(self):
        for scope, kind in (('smoke', 'vm'), ('invalid', 'vm'), ('smoke', 'invalid')):
            with self.assertRaises(ValueError):
                matrix([], ROOT.name, scope, kind)

    def test_legacy_entrypoints_use_the_validated_suite_and_propagate_failure(self):
        target = yaml.safe_load((ROOT / '.github/workflows/hosted-tests.yml').read_text())
        self.assertIn('workflow_call', target['on'])
        for filename, kind in (('test.yml', 'container'), ('test_kvm.yml', 'vm')):
            caller = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text())
            job = caller['jobs']['validate-published']
            self.assertEqual(job['uses'], './.github/workflows/hosted-tests.yml')
            self.assertEqual(job['with']['kind'], kind)
            self.assertFalse(job.get('continue-on-error', False))


if __name__ == '__main__':
    unittest.main()
