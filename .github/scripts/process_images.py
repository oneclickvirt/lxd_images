#!/usr/bin/env python3
"""Refresh processed image pairs while keeping the last valid pair on failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import zipfile
from release_assets import Publisher

NAME = re.compile(r'^([A-Za-z0-9]+)_([A-Za-z0-9.-]+)_([A-Za-z0-9.-]+)_([A-Za-z0-9_-]+)_([A-Za-z0-9_-]+)\.zip$')


def sources(publisher):
    values = {}
    for page in range(1, 21):
        releases = publisher.request(publisher.base+f'/releases?per_page=100&page={page}')
        for release in releases:
            if release['tag_name'] in ['processed', 'kvm_images'] or release['draft'] or release['prerelease']:
                continue
            for asset in publisher.assets(release['id']).values():
                if not NAME.fullmatch(asset['name']):
                    continue
                previous = values.get(asset['name'])
                if previous is None or asset['updated_at'] > previous['updated_at']:
                    values[asset['name']] = asset
        if len(releases) < 100:
            return list(values.values())
    raise RuntimeError('source release pagination exceeded')


def processed_pair_names(asset, metadata):
    match = NAME.fullmatch(asset['name'])
    if not match:
        raise ValueError('invalid source image asset name')
    os_name, version, _, arch, variant = match.groups()
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(arch, arch)
    prefix = f'{os_name}-{version}-{arch}-{variant}-'
    return [prefix + 'rootfs.squashfs', prefix + metadata + '.tar.xz']


def has_processed_pair(publisher, asset, metadata):
    release = publisher.ensure_release('processed')
    available = publisher.assets(release['id'])
    return all(name in available and available[name].get('state') == 'uploaded' and available[name].get('size', 0) > 0
               for name in processed_pair_names(asset, metadata))


def source_label(asset, metadata):
    # A missing source identity must cause a rebuild, never a cache hit.
    if not asset.get('id') or not asset.get('size') or not asset.get('updated_at'):
        return None
    identity = {key: asset.get(key) for key in ('id', 'name', 'size', 'digest', 'updated_at')}
    identity['metadata'] = metadata
    return 'image-source-v1:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def unchanged_pair(available, asset, metadata):
    label = source_label(asset, metadata)
    if label is None:
        return False
    pair = [available.get(name, {}) for name in processed_pair_names(asset, metadata)]
    return all(row.get('state') == 'uploaded' and row.get('size', 0) > 0
               and row.get('label') == label
               and re.fullmatch(r'sha256:[0-9a-f]{64}', row.get('digest') or '')
               for row in pair)


def failure_detail(error):
    if isinstance(error, urllib.error.HTTPError):
        return f'HTTP {error.code} {error.reason}'
    if isinstance(error, subprocess.CalledProcessError):
        return f'command exited with status {error.returncode}'
    detail = str(error).splitlines()[0] if str(error) else ''
    detail = re.sub(r'https?://\S+', '[URL]', detail)
    detail = re.sub(r'(?i)(authorization|token|password|secret)([=: ]+)\S+', r'\1\2[redacted]', detail)
    return type(error).__name__ + (': ' + detail[:300] if detail else '')


def process(publisher, asset, metadata):
    match = NAME.fullmatch(asset['name'])
    os_name, version, codename, arch, variant = match.groups()
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(arch, arch)
    with tempfile.TemporaryDirectory(prefix='process-image-', dir=os.environ.get('RUNNER_TEMP')) as temp:
        folder = Path(temp)
        archive = folder/'source.zip'
        subprocess.run(['curl','--fail','--location','--connect-timeout','15','--max-time','1200',
                        '--retry','3','--retry-max-time','180','--retry-connrefused','-o',str(archive),
                        asset['browser_download_url']], check=True, timeout=1600)
        if archive.stat().st_size != asset['size']:
            raise RuntimeError('downloaded archive size mismatch')
        if asset.get('digest') and asset['digest'] != 'sha256:' + publisher.digest(archive):
            raise RuntimeError('downloaded archive checksum mismatch')
        paths = []
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            for member in ['rootfs.squashfs', metadata+'.tar.xz']:
                matches = [name for name in names if Path(name).name == member and not name.endswith('/')]
                if len(matches) != 1:
                    raise RuntimeError('missing or ambiguous image pair')
                entry = z.getinfo(matches[0])
                if entry.file_size == 0 or entry.file_size > 2147483648:
                    raise RuntimeError('image pair outside release limits')
                if shutil.disk_usage(folder).free < entry.file_size+1024*1024*1024:
                    raise RuntimeError('insufficient image processing disk space')
                filename = f'{os_name}-{version}-{arch}-{variant}-{member}'
                path = folder/filename
                with z.open(entry) as source, path.open('wb') as output:
                    shutil.copyfileobj(source,output,length=1024*1024)
                paths.append(path)
        subprocess.run(['tar','-tJf',str(paths[1])], check=True, stdout=subprocess.DEVNULL, timeout=120)
        # Metadata and rootfs are a single replacement set, including rollback.
        publisher.publish('processed', paths)
        label = source_label(asset, metadata)
        if label:
            # Label both members only after transactional publication succeeds.
            release = publisher.ensure_release('processed')
            available = publisher.assets(release['id'])
            for path in paths:
                row = available[path.name]
                publisher.request(publisher.base + '/releases/assets/' + str(row['id']),
                                  'PATCH', {'label': label})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--metadata',choices=['incus','lxd'],required=True)
    args=parser.parse_args()
    publisher=Publisher(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    assets=sources(publisher)
    if not assets:
        raise RuntimeError('no valid source image archives')
    failures=[]
    fallback_count=0
    unchanged_count=0
    release=publisher.ensure_release('processed')
    available=publisher.assets(release['id'])
    for asset in assets:
        try:
            if unchanged_pair(available,asset,args.metadata):
                unchanged_count += 1
                print('Reused unchanged verified image pair:',asset['name'],flush=True)
                continue
            process(publisher,asset,args.metadata)
            print('Published valid image pair:',asset['name'],flush=True)
        except Exception as exc:
            detail = failure_detail(exc)
            try:
                fallback = has_processed_pair(publisher, asset, args.metadata)
            except Exception as fallback_error:
                fallback = False
                detail += '; fallback lookup failed: ' + failure_detail(fallback_error)
            if fallback:
                fallback_count += 1
                print('Image pair refresh failed; retaining the previously validated pair:', asset['name'], detail)
            else:
                failures.append(asset['name'])
                print('Image pair refresh failed with no valid fallback:', asset['name'], detail, file=sys.stderr)
    if failures:
        raise RuntimeError(f'{len(failures)} image pairs failed without a complete previous pair: {", ".join(failures)}')
    print('Processed image refresh completed:',len(assets),'; reused previous pairs:',fallback_count,
          '; unchanged verified pairs:',unchanged_count)


if __name__=='__main__':
    main()
