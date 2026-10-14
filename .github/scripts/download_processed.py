#!/usr/bin/env python3
"""Download only complete verified image pairs for a new simplestreams index."""
import argparse
import datetime
import os
from pathlib import Path
import re
import subprocess
import tarfile
from release_assets import Publisher


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--metadata',choices=['incus','lxd'],required=True)
    args=parser.parse_args()
    publisher=Publisher(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_TOKEN'])
    release=publisher.request(publisher.base+'/releases/tags/processed')
    pattern=re.compile(r'^([A-Za-z0-9]+)-(.+?)-(amd64|arm64|x86_64|aarch64)-(.+?)-(rootfs|'+args.metadata+r')\.(squashfs|tar\.xz)$')
    pairs={}
    for asset in publisher.assets(release['id']).values():
        match=pattern.fullmatch(asset['name'])
        if not match or asset.get('state')!='uploaded' or not asset.get('size'):
            continue
        os_name,release_name,arch,variant,kind,ext=match.groups()
        if variant=='default':continue
        if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',part) or part in ['.','..'] for part in [os_name,release_name,arch,variant]):
            raise RuntimeError('invalid processed image identity')
        pairs.setdefault((os_name,release_name,arch,variant),{})[kind]=asset
    if not pairs:
        raise RuntimeError('no complete processed images available')
    timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M')
    for identity,parts in pairs.items():
        if set(parts)!= {'rootfs',args.metadata}:
            raise RuntimeError('processed release contains an incomplete image pair')
        os_name,release_name,arch,variant=identity
        folder=Path('build/spiritlhl').joinpath(*identity,timestamp)
        folder.mkdir(parents=True,exist_ok=True)
        for kind,asset in parts.items():
            path=folder/('rootfs.squashfs' if kind=='rootfs' else args.metadata+'.tar.xz')
            temporary=path.with_suffix(path.suffix+'.partial')
            subprocess.run(['curl','--fail','--location','--connect-timeout','15','--max-time','1200',
                            '--retry','3','--retry-max-time','180','--retry-connrefused',
                            '-o',str(temporary),asset['browser_download_url']],check=True,timeout=1600)
            if temporary.stat().st_size!=asset['size']:
                raise RuntimeError('processed download size mismatch')
            if asset.get('digest') and asset['digest']!='sha256:'+Publisher.digest(temporary):
                raise RuntimeError('processed download checksum mismatch')
            temporary.rename(path)
        # Deploy time is not image build time. Read the authenticated image metadata.
        with tarfile.open(folder/(args.metadata+'.tar.xz'), 'r:xz') as archive:
            member=next((entry for entry in archive if entry.name.removeprefix('./')=='metadata.yaml'),None)
            if member is None or not 0<member.size<262144:
                raise RuntimeError('image creation metadata is missing')
            payload=archive.extractfile(member).read().decode()
        match=re.search(r'^creation_date:\s*["\']?([0-9]{9,12})["\']?\s*$',payload,re.MULTILINE)
        if not match:
            raise RuntimeError('actual image creation timestamp is missing')
        created=datetime.datetime.fromtimestamp(int(match[1]),datetime.timezone.utc)
        if created.year<2000 or created>datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1):
            raise RuntimeError('actual image creation timestamp is invalid')
        timestamp=created.strftime('%Y%m%d_%H%M')
        target=folder.parent/timestamp
        if target!=folder:
            folder.rename(target);folder=target
        (folder/'meta.yaml').write_text(f'architecture: {arch}\nos: {os_name}\nrelease: {release_name}\nvariant: {variant}\ntype: {args.metadata}\ncreated_at: {timestamp}\n')
    print('Verified complete image pairs:',len(pairs))


if __name__=='__main__':
    main()
