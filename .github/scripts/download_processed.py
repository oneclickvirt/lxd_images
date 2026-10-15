#!/usr/bin/env python3
"""Download only complete verified image pairs for a new simplestreams index."""
import argparse
import datetime
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from release_assets import Publisher


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_asset(publisher, asset, path, budget=600):
    # Release names are mutable and their public URLs may still serve cached
    # bytes after replacement. Resolve the immutable asset ID through the API.
    request = urllib.request.Request(
        'https://api.github.com' + publisher.base + '/releases/assets/' + str(int(asset['id']))
        + '?_ci_read=' + str(time.time_ns()),
        headers={'Accept': 'application/octet-stream', 'Authorization': 'Bearer ' + publisher.credential,
                 'X-GitHub-Api-Version': '2022-11-28', 'Cache-Control': 'no-cache'})
    try:
        response = urllib.request.build_opener(NoRedirect()).open(request, timeout=min(45, budget))
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers.get('Location', '')
        parsed = urllib.parse.urlparse(location)
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.hostname not in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com',
                                           'github-releases.githubusercontent.com', 'github.com')):
            raise RuntimeError('unexpected image asset redirect') from None
        # No Authorization header is forwarded to the asset host.
        subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
                        '--connect-timeout', '15', '--max-time', str(max(1, int(budget - 45))), '--retry', '2',
                        '--retry-max-time', '90', '--retry-connrefused', '-o', str(path), location],
                       check=True, timeout=budget + 5)
    else:
        with response, path.open('wb') as output:
            if 'json' in response.headers.get('Content-Type', ''):
                raise RuntimeError('asset API returned metadata instead of image bytes')
            size = 0
            deadline = time.monotonic() + budget
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > asset['size'] or time.monotonic() > deadline:
                    raise RuntimeError('image asset exceeded download limits')
                output.write(block)


def download_pair(publisher, release_id, names, parts, metadata, folder, downloader=None, pause=time.sleep):
    """Retry a concurrently replaced pair, retaining size/digest/identity gates."""
    downloader = downloader or download_asset
    kinds = ('rootfs', metadata)
    deadline = time.monotonic() + 900
    for attempt in range(3):
        if time.monotonic() >= deadline:
            raise RuntimeError('processed image pair download budget exhausted')
        try:
            if attempt:
                available = publisher.assets(release_id)
                parts = {kind: available.get(names[kind]) for kind in kinds}
            if any(not parts.get(kind) for kind in kinds):
                raise RuntimeError('processed release contains an incomplete image pair')
            labels = [parts[kind].get('label') for kind in kinds]
            if labels[0] != labels[1]:
                raise RuntimeError('processed image pair changed during publication')
            for kind in kinds:
                asset = parts[kind]
                if (asset.get('state') != 'uploaded' or not asset.get('size')
                        or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or '')):
                    raise RuntimeError('processed image identity is incomplete')
                path = folder / ('rootfs.squashfs' if kind == 'rootfs' else metadata + '.tar.xz')
                temporary = path.with_suffix(path.suffix + '.partial')
                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    raise RuntimeError('processed image pair download budget exhausted')
                downloader(publisher, asset, temporary, budget=min(600, remaining))
                if temporary.stat().st_size != asset['size']:
                    raise RuntimeError('processed download size mismatch')
                if asset['digest'] != 'sha256:' + Publisher.digest(temporary):
                    raise RuntimeError('processed download checksum mismatch')
                temporary.replace(path)
            return
        except (OSError, RuntimeError, subprocess.SubprocessError):
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
            if attempt == 2:
                raise
            print('Processed pair changed or download failed; retrying a fresh verified snapshot:', names['rootfs'])
            pause(2 ** attempt)


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
        os_name,release_name,arch,variant=identity
        folder=Path('build/spiritlhl').joinpath(*identity,timestamp)
        folder.mkdir(parents=True,exist_ok=True)
        prefix = '-'.join(identity) + '-'
        names = {'rootfs': prefix + 'rootfs.squashfs', args.metadata: prefix + args.metadata + '.tar.xz'}
        download_pair(publisher, release['id'], names, parts, args.metadata, folder)
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
