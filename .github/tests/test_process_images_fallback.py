from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
process_images = importlib.import_module('process_images')


class FakePublisher:
    def __init__(self, assets):
        self.available = assets

    def ensure_release(self, tag):
        self.asserted_tag = tag
        return {'id': 1}

    def assets(self, release_id):
        return self.available


class ProcessImageFallbackTests(unittest.TestCase):
    def setUp(self):
        self.asset = {'name': 'almalinux_9_9_aarch64_cloud.zip', 'updated_at': '2026-10-14T00:00:00Z'}
        self.pair = process_images.processed_pair_names(self.asset, 'lxd')

    def test_only_a_complete_uploaded_pair_counts_as_fallback(self):
        complete = {name: {'state': 'uploaded', 'size': 1} for name in self.pair}
        self.assertTrue(process_images.has_processed_pair(FakePublisher(complete), self.asset, 'lxd'))
        del complete[self.pair[1]]
        self.assertFalse(process_images.has_processed_pair(FakePublisher(complete), self.asset, 'lxd'))

    def test_refresh_failure_uses_existing_pair_and_keeps_workflow_green(self):
        assets = {name: {'state': 'uploaded', 'size': 1} for name in self.pair}
        publisher = FakePublisher(assets)
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {'GITHUB_REPOSITORY': 'oneclickvirt/lxd_images', 'GH_TOKEN': 'fixture'}), \
             mock.patch.object(process_images, 'Publisher', return_value=publisher), \
             mock.patch.object(process_images, 'sources', return_value=[self.asset]), \
             mock.patch.object(process_images, 'process', side_effect=RuntimeError('source mirror timed out')), \
             mock.patch.object(sys, 'argv', ['process_images.py', '--metadata', 'lxd']), \
             redirect_stdout(stdout):
            process_images.main()
        self.assertIn('retaining the previously validated pair', stdout.getvalue())
        self.assertIn('source mirror timed out', stdout.getvalue())
        self.assertIn('reused previous pairs: 1', stdout.getvalue())

    def test_refresh_failure_without_complete_pair_still_fails(self):
        publisher = FakePublisher({self.pair[0]: {'state': 'uploaded', 'size': 1}})
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {'GITHUB_REPOSITORY': 'oneclickvirt/lxd_images', 'GH_TOKEN': 'fixture'}), \
             mock.patch.object(process_images, 'Publisher', return_value=publisher), \
             mock.patch.object(process_images, 'sources', return_value=[self.asset]), \
             mock.patch.object(process_images, 'process', side_effect=RuntimeError('source mirror timed out')), \
             mock.patch.object(sys, 'argv', ['process_images.py', '--metadata', 'lxd']), \
             redirect_stderr(stderr), self.assertRaisesRegex(RuntimeError, 'without a complete previous pair'):
            process_images.main()
        self.assertIn('source mirror timed out', stderr.getvalue())

    def test_failure_details_redact_urls_and_credentials(self):
        detail = process_images.failure_detail(RuntimeError('failed https://example.invalid/x?token=secret TOKEN=secret'))
        self.assertNotIn('example.invalid', detail)
        self.assertNotIn('secret', detail)
        self.assertIn('[URL]', detail)
        self.assertIn('[redacted]', detail)

    def test_source_list_keeps_only_the_latest_copy_of_an_asset(self):
        source = {'name': self.asset['name']}
        class SourcePublisher:
            base = '/repos/oneclickvirt/lxd_images'
            def request(self, path):
                return [{'id': 1, 'tag_name': 'old', 'draft': False, 'prerelease': False},
                        {'id': 2, 'tag_name': 'new', 'draft': False, 'prerelease': False}]
            def assets(self, release_id):
                value = dict(source, updated_at='2026-10-13T00:00:00Z' if release_id == 1 else '2026-10-14T00:00:00Z')
                return {value['name']: value}
        result = process_images.sources(SourcePublisher())
        self.assertEqual(1, len(result))
        self.assertEqual('2026-10-14T00:00:00Z', result[0]['updated_at'])


if __name__ == '__main__':
    unittest.main()
