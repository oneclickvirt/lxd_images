"""Concurrent replacement and stale release URLs cannot corrupt a portal pair."""
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import download_processed as processed


class ProcessedSnapshotTests(unittest.TestCase):
    def pair(self, label='snapshot', offset=0):
        names = {'rootfs': 'debian-13-arm64-cloud-rootfs.squashfs',
                 'incus': 'debian-13-arm64-cloud-incus.tar.xz'}
        parts = {kind: {'id': index + 1 + offset, 'name': name, 'state': 'uploaded',
                        'size': len(kind.encode()), 'digest': 'sha256:' + hashlib.sha256(kind.encode()).hexdigest(),
                        'label': label}
                 for index, (kind, name) in enumerate(names.items())}
        return names, parts

    def test_stale_bytes_retry_with_fresh_pair_and_no_partial_files(self):
        names, initial = self.pair('old')
        _, fresh = self.pair('new', 10)
        publisher = SimpleNamespace(assets=mock.Mock(return_value={p['name']: p for p in fresh.values()}))
        calls = []
        def download(pub, asset, path, budget):
            calls.append(asset['id'])
            kind = 'rootfs' if asset['name'].endswith('squashfs') else 'incus'
            path.write_bytes(b'stale content' if asset['id'] < 10 else kind.encode())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            processed.download_pair(publisher, 1, names, initial, 'incus', folder, download, lambda _: None)
            self.assertEqual((folder / 'rootfs.squashfs').read_bytes(), b'rootfs')
            self.assertEqual((folder / 'incus.tar.xz').read_bytes(), b'incus')
            self.assertFalse(list(folder.glob('*.partial')))
        self.assertEqual(calls, [1, 11, 12])

    def test_mixed_or_incomplete_publication_is_reloaded_before_download(self):
        names, fresh = self.pair('consistent', 10)
        publisher = SimpleNamespace(assets=mock.Mock(return_value={p['name']: p for p in fresh.values()}))
        for initial in ({'rootfs': fresh['rootfs']},
                        dict(fresh, incus=dict(fresh['incus'], label='different-source'))):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as temporary:
                def download(pub, asset, path, budget):
                    path.write_bytes(b'rootfs' if asset['name'].endswith('squashfs') else b'incus')
                processed.download_pair(publisher, 1, names, initial, 'incus', Path(temporary), download, lambda _: None)

    def test_persistent_corruption_fails_after_three_attempts(self):
        names, parts = self.pair()
        publisher = SimpleNamespace(assets=mock.Mock(return_value={p['name']: p for p in parts.values()}))
        attempts = []
        def corrupt(pub, asset, path, budget):
            attempts.append(asset['id'])
            path.write_bytes(b'xxxxxx')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                processed.download_pair(publisher, 1, names, parts, 'incus', folder, corrupt, lambda _: None)
            self.assertFalse(list(folder.iterdir()))
        self.assertEqual(len(attempts), 3)

    def test_asset_id_redirect_does_not_forward_api_authorization(self):
        publisher = SimpleNamespace(base='/repos/oneclickvirt/incus_images', credential='fixture-secret')
        location = 'https://release-assets.githubusercontent.com/public-image'
        redirect = urllib.error.HTTPError('https://api.github.com/asset', 302, 'Found', {'Location': location}, io.BytesIO())
        opener = mock.Mock()
        opener.open.side_effect = redirect
        with mock.patch.object(processed.urllib.request, 'build_opener', return_value=opener), \
             mock.patch.object(processed.subprocess, 'run') as curl:
            processed.download_asset(publisher, {'id': 42}, Path('image.partial'))
        request = opener.open.call_args.args[0]
        self.assertIn('/releases/assets/42?', request.full_url)
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-secret')
        self.assertNotIn('fixture-secret', repr(curl.call_args))
        self.assertFalse(any('authorization' in arg.lower() for arg in curl.call_args.args[0]))

    def test_untrusted_redirect_is_rejected(self):
        publisher = SimpleNamespace(base='/repos/oneclickvirt/incus_images', credential='fixture-secret')
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError('https://api.github.com/asset', 302, 'Found',
            {'Location': 'https://untrusted.example/image'}, io.BytesIO())
        with mock.patch.object(processed.urllib.request, 'build_opener', return_value=opener), \
             mock.patch.object(processed.subprocess, 'run') as curl:
            with self.assertRaisesRegex(RuntimeError, 'unexpected image asset redirect'):
                processed.download_asset(publisher, {'id': 42}, Path('image.partial'))
        curl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
