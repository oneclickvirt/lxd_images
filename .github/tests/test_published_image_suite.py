from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
import published_image_suite as suite
from published_image_suite import matrix, automatic_published_matrix


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

    def test_automated_suite_holds_only_the_quarantined_arch_and_kind(self):
        entry = {'distro': 'debian', 'release': 'trixie', 'arch': 'arm64', 'kind': 'vm',
                 'reason': 'Confirmed guest readiness failure',
                 'evidence': 'https://github.com/oneclickvirt/incus_images/actions/runs/123'}
        policy = {'schema': 1, 'entries': [entry]}
        value = matrix(self.assets, ROOT.name, 'full', 'vm')
        filtered = automatic_published_matrix(value, policy, 'vm')
        self.assertEqual([row['image'] for row in filtered['include']], [self.assets[-1]['name']])
        self.assertEqual(len(value['include']), 3)  # Manual selection remains intact.
        containers = matrix(self.assets, ROOT.name, 'full', 'container')
        self.assertEqual(automatic_published_matrix(containers, policy, 'container'), containers)
        with self.assertRaises(ValueError):
            automatic_published_matrix(value, {'schema': 1, 'entries': [entry, entry]}, 'vm')

    def test_empty_automated_suite_is_explicit_and_manual_repair_still_selects_asset(self):
        entry = {'distro': 'debian', 'release': 'trixie', 'arch': 'arm64', 'kind': 'vm',
                 'reason': 'Confirmed guest readiness failure',
                 'evidence': 'https://github.com/oneclickvirt/incus_images/actions/runs/123'}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / '.github').mkdir()
            (folder / '.github/image-build-quarantine.json').write_text(json.dumps({'schema': 1, 'entries': [entry]}))
            previous = Path.cwd()
            try:
                os.chdir(folder)
                for automatic, count in [('true', 0), ('false', 1)]:
                    output = folder / ('output-' + automatic)
                    summary = folder / ('summary-' + automatic)
                    environment = {'GITHUB_REPOSITORY': 'oneclickvirt/' + ROOT.name,
                                   'GH_TOKEN': 'fixture', 'CI_IMAGE_AUTOMATIC': automatic,
                                   'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
                                   'IMAGE': self.assets[2]['name']}
                    with mock.patch.dict(os.environ, environment, clear=True), \
                         mock.patch.object(sys, 'argv', ['suite', 'matrix', '--kind', 'vm']), \
                         mock.patch.object(suite, 'Publisher'), \
                         mock.patch.object(suite, 'published', return_value=[self.assets[2]]):
                        suite.main()
                    fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
                    self.assertEqual(fields['count'], str(count))
                    self.assertEqual(len(json.loads(fields['matrix'])['include']), count)
                    if automatic == 'true':
                        self.assertIn('0 selected, 1 known-broken tuples held', summary.read_text())
                        self.assertNotIn('IMAGE_TEST_RESULT', summary.read_text())
            finally:
                os.chdir(previous)

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
