#!/usr/bin/env python3
"""Refresh processed image pairs while keeping the last valid pair on failure."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from release_assets import Publisher

NAME = re.compile(r'^([A-Za-z0-9]+)_([A-Za-z0-9.-]+)_([A-Za-z0-9.-]+)_([A-Za-z0-9_-]+)_([A-Za-z0-9_-]+)\.zip$')


def sources(publisher):
    values = []
    for page in range(1, 21):
        releases = publisher.request(publisher.base+f'/releases?per_page=100&page={page}')
        for release in releases:
            if release['tag_name'] in ['processed', 'kvm_images'] or release['draft'] or release['prerelease']:
                continue
            values.extend(asset for asset in publisher.assets(release['id']).values() if NAME.fullmatch(asset['name']))
        if len(releases) < 100:
            return values
    raise RuntimeError('source release pagination exceeded')


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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--metadata',choices=['incus','lxd'],required=True)
    args=parser.parse_args()
    publisher=Publisher(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    assets=sources(publisher)
    if not assets:
        raise RuntimeError('no valid source image archives')
    failures=[]
    for asset in assets:
        try:
            process(publisher,asset,args.metadata)
            print('Published valid image pair:',asset['name'])
        except Exception as exc:
            failures.append(asset['name'])
            print('Image pair refresh failed:',asset['name'],type(exc).__name__)
    if failures:
        raise RuntimeError(f'{len(failures)} image pairs failed; previous pairs retained where available')
    print('Processed image refresh completed:',len(assets))


if __name__=='__main__':
    main()
