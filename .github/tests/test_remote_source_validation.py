import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('validate_image_remote', ROOT / '.github/scripts/validate_image_remote.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class RemoteSourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.build = {'schema': 1, 'flavour': 'lxd', 'products': 58, 'layout_sha256': 'a' * 64}
        self.images = [{'fingerprint': 'b' * 64, 'architecture': 'x86_64'}]

    def test_accepts_anonymous_simple_streams_images_without_public_flag(self):
        self.assertEqual(1, validator.validate(self.images, self.build, 'lxd'))

    def test_diagnostic_reports_only_sanitized_counts_and_checks(self):
        summary = validator.diagnostic(self.images, self.build, 'lxd')
        self.assertIn('Client image records: `1`', summary)
        self.assertIn('Records with architecture: `1`', summary)
        self.assertIn('Portal flavour matches: `True`', summary)
        self.assertNotIn('b' * 64, summary)

    def test_rejects_empty_listing(self):
        with self.assertRaisesRegex(ValueError, 'no images'):
            validator.validate([], self.build, 'lxd')

    def test_rejects_malformed_image_records(self):
        with self.assertRaisesRegex(ValueError, 'malformed images'):
            validator.validate([{'fingerprint': '', 'architecture': 'x86_64'}], self.build, 'lxd')

    def test_rejects_wrong_portal_flavour_and_invalid_layout_hash(self):
        with self.assertRaisesRegex(ValueError, 'flavour'):
            validator.validate(self.images, dict(self.build, flavour='incus'), 'lxd')
        with self.assertRaisesRegex(ValueError, 'layout identity'):
            validator.validate(self.images, dict(self.build, layout_sha256='invalid'), 'lxd')


if __name__ == '__main__':
    unittest.main()
