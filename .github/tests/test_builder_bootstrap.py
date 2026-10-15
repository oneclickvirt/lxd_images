"""Bootstrap compatibility must keep package signature verification enabled."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from patch_lxd_builder import oracle_source, rocky_source


class BuilderBootstrapTests(unittest.TestCase):
    def test_oracle_versioned_iso_names_cover_both_architectures(self):
        source = '''if s.definition.Image.Release == "9" {
            fname = fmt.Sprintf("OracleLinux-R9-U%d-%s-boot.iso", i, s.architecture)
            fname = fmt.Sprintf("OracleLinux-R9-U%d-%s-dvd.iso", i, s.architecture)
        }'''
        updated = oracle_source(source)
        self.assertEqual(oracle_source(updated), updated)
        self.assertIn('s.majorVersion == "8"', updated)
        self.assertIn('s.majorVersion == "10"', updated)
        self.assertIn('OracleLinux-R%s-U%d-%s-dvd.iso', updated)
        self.assertNotIn('OracleLinux-R9-', updated)
        with self.assertRaises(ValueError):
            oracle_source('unexpected upstream contract')

    def test_vendor_key_is_scoped_to_rocky10_and_integrity_checked(self):
        key = (Path(__file__).resolve().parents[1] / 'scripts/rocky-10.asc').read_bytes()
        source = 'mkdir -p /etc/yum.repos.d\nif [ -d /mnt/cdrom ]; then\ngpgcheck=1\nfi'
        updated = rocky_source(source, key)
        self.assertEqual(rocky_source(updated, key), updated)
        self.assertIn('if [ "${RELEASE}" = 10 ]; then', updated)
        self.assertIn('gpgcheck=1', updated)
        self.assertNotIn('gpgcheck=0', updated)
        self.assertLess(updated.index('HOSTED_ROCKY_KEY'), updated.index('if [ -d /mnt/cdrom ]'))
        with self.assertRaises(ValueError):
            rocky_source(source, key + b'corrupt')
        with self.assertRaises(ValueError):
            rocky_source('unexpected upstream contract', key)


if __name__ == '__main__':
    unittest.main()
