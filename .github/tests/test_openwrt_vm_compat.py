"""Verify the real upstream OpenWrt source and procd generator transformations."""
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from patch_lxd_builder import openwrt_source, openwrt_agent, openwrt_release_test, signature_tests, fixture
from refresh_image_sources import current_openwrt_for_lxd


FIXTURES = Path(__file__).with_name('fixtures')


class OpenWrtVMCompatibilityTests(unittest.TestCase):
    def test_combined_source_retains_signature_and_partition_validation(self):
        source = (FIXTURES / 'canonical-openwrt-http.go.txt').read_text()
        updated = openwrt_source(source)
        self.assertEqual(openwrt_source(updated), updated)
        for marker in ('generic-ext4-combined-efi.img.gz', 'sha256sums.asc', 's.VerifyFile(',
                       'len(matches) != 2', 'unix.Unmount(', 'Failed to copy esp:'):
            self.assertIn(marker, updated)
        self.assertNotIn('github.com/lxc/distrobuilder/v3/shared', updated)
        with self.assertRaises(ValueError):
            openwrt_source('upstream source contract changed')

    def test_real_agent_dispatch_and_procd_lifecycle_are_added_once(self):
        source = (FIXTURES / 'canonical-lxd-agent.go.txt').read_text()
        updated = openwrt_agent(source)
        self.assertEqual(openwrt_agent(updated), updated)
        self.assertLess(updated.index('"openwrt_version"'), updated.index('if fi.Mode()&os.ModeSymlink'))
        for marker in ('S05lxd-agent', 'K85lxd-agent', 'exec /run/lxd_agent/lxd-agent', '[]byte(lxdAgentSetupScript)'):
            self.assertIn(marker, updated)
        self.assertEqual(updated.count('func (g *lxdAgent) handleProcd() error'), 1)
        with self.assertRaises(ValueError):
            openwrt_agent('upstream agent contract changed')

    def test_archived_and_current_parser_tests_retain_all_release_assertions(self):
        for name in ('canonical-openwrt-release-test.go.txt', 'fallback-openwrt-release-test.go.txt'):
            with self.subTest(name=name):
                original = (FIXTURES / name).read_text()
                updated = openwrt_release_test(original)
                self.assertEqual(openwrt_release_test(updated), updated)
                for assertion in ('require.NoError(t, err)', 'require.Regexp(t, tt.want, release)', '"21.02"', '"22.03"', '"23.05"'):
                    self.assertIn(assertion, updated)
                self.assertIn('s.client = server.Client()', updated)
                self.assertNotIn('https://downloads.openwrt.org/releases/', updated)

    def test_offline_signature_tests_preserve_every_valid_and_invalid_signature_case(self):
        original = (FIXTURES / 'canonical-signature-tests.go.txt').read_text()
        updated = signature_tests(original)
        self.assertEqual(signature_tests(updated), updated)
        for assertion in ('require.Error(t, err)', 'require.False(t, valid)', 'require.True(t, valid)',
                          'testfile-invalid.asc', 'testfile.gpg', 'testfile.sig', 'testfile.asc',
                          '"no keys"', '"invalid key"'):
            self.assertIn(assertion, updated)
        self.assertIn('hosted-wrong-public.asc', updated)
        self.assertNotIn('0x5DE8949A899C8D99', updated)
        self.assertTrue(fixture('upstream-test-public-key.asc').startswith('-----BEGIN PGP PUBLIC KEY BLOCK-----'))

    def test_current_recipe_translation_preserves_keys_hooks_and_customization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'images_yaml').mkdir()
            (root / 'sh_insert_content.text').write_text('- trigger: post-files\n  action: echo fixture customization\n')
            document = {'image': {'distribution': 'OpenWrt'},
                        'source': {'downloader': 'openwrt-http', 'url': 'https://downloads.openwrt.org', 'keys': ['vendor-key']},
                        'targets': {'incus': {'vm': {'filesystem': 'ext4'}}},
                        'files': [{'generator': 'incus-agent', 'types': ['vm']}],
                        'actions': [{'trigger': 'post-files', 'types': ['vm'], 'action': 'echo ${DISTROBUILDER_ROOT_PARTUUID}'}]}
            current_openwrt_for_lxd(root, yaml.safe_dump(document))
            updated = yaml.safe_load((root / 'images_yaml/openwrt.yaml').read_text())
            self.assertEqual(updated['source'], document['source'])
            self.assertEqual(updated['targets'], {'lxd': {'vm': {'filesystem': 'ext4'}}})
            self.assertEqual(updated['files'][0]['generator'], 'lxd-agent')
            self.assertEqual(updated['actions'][0]['action'], 'echo ${LXD_IMAGEBUILDER_ROOT_PARTUUID}')
            self.assertEqual(updated['actions'][-1]['action'], 'echo fixture customization')


if __name__ == '__main__':
    unittest.main()
