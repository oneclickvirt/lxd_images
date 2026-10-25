#!/usr/bin/env python3
"""Check every published openEuler pair against its source before runtime tests."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile
from release_assets import Publisher
from process_images import sources, processed_pair_names


def sha(stream):
    return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def download(asset, destination, publisher):
    if asset.get('state') != 'uploaded' or not asset.get('size'):
        raise RuntimeError('Incomplete published asset')
    environment = dict(os.environ)
    environment.pop('GH_TOKEN', None)
    environment.pop('GITHUB_TOKEN', None)
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3',
                    '--connect-timeout', '15', '--max-time', '900', '-o', str(destination),
                    asset['browser_download_url']], check=True, timeout=1200, env=environment)
    if destination.stat().st_size != asset['size']:
        raise RuntimeError('Published asset size mismatch')
    digest = 'sha256:' + publisher.digest(destination)
    if asset.get('digest') and asset['digest'] != digest:
        raise RuntimeError('Published asset digest mismatch')
    print('Verified published asset:', asset['name'], asset['id'], digest, flush=True)
    return digest


def main():
    publisher = Publisher(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    runtime = {'incus_images': 'incus', 'lxd_images': 'lxd'}[os.environ['GITHUB_REPOSITORY'].split('/')[-1]]
    originals = [a for a in sources(publisher) if a['name'].startswith('openeuler_')]
    processed_release = publisher.request(publisher.base + '/releases/tags/processed')
    processed = publisher.assets(processed_release['id'])
    if sys.argv[1] == 'matrix':
        rows = []
        for asset in sorted(originals, key=lambda a: a['name']):
            names = processed_pair_names(asset, runtime)
            if not all(name in processed for name in names):
                raise RuntimeError('Missing processed image pair: ' + asset['name'])
            arch = 'arm64' if re.search(r'_(arm64|aarch64)_', asset['name']) else 'amd64'
            rows.append({'image': asset['name'], 'arch': arch,
                         'runner': 'ubuntu-24.04-arm' if arch == 'arm64' else 'ubuntu-24.04'})
        if not rows or len(rows) > 256:
            raise RuntimeError('Empty or oversized processed image suite')
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            print('matrix=' + json.dumps({'include': rows}, separators=(',', ':')), file=stream)
        print('Published openEuler image pairs:', len(rows))
        return
    if sys.argv[1] != 'download':
        raise ValueError('Unknown verification command')
    matches = [a for a in originals if a['name'] == os.environ['IMAGE']]
    if len(matches) != 1:
        raise RuntimeError('Missing or ambiguous source archive')
    asset = matches[0]
    names = processed_pair_names(asset, runtime)
    output = Path('processed')
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='euler-processed-', dir=os.environ['RUNNER_TEMP']) as temporary:
        folder = Path(temporary)
        original = folder / 'source.zip'
        download(asset, original, publisher)
        pair = {}
        for name, member in zip(names, ('rootfs.squashfs', runtime + '.tar.xz'), strict=True):
            path = folder / member
            row = processed[name]
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', row.get('digest') or ''):
                raise RuntimeError('Processed image pair is missing its SHA256 digest')
            pair[member] = (path, download(row, path, publisher))
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(output / asset['name'], 'w', compression=zipfile.ZIP_STORED) as target:
            for member, (path, digest) in pair.items():
                entries = [info for info in source.infolist() if Path(info.filename).name == member and not info.is_dir()]
                if len(entries) != 1 or entries[0].file_size != path.stat().st_size:
                    raise RuntimeError('Processed image pair does not match source archive')
                with source.open(entries[0]) as stream:
                    if sha(stream) != digest:
                        raise RuntimeError('Processed image content differs from source archive')
                target.write(path, member)
        print('Processed rootfs and metadata exactly match source:', asset['name'], flush=True)


if __name__ == '__main__':
    main()
