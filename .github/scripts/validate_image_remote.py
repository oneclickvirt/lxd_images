#!/usr/bin/env python3
"""Validate an anonymous Incus client listing and the published portal identity."""
import argparse
import json
import os
from pathlib import Path
import re


SHA256 = re.compile(r'^[0-9a-f]{64}$')


def diagnostic(images, build, flavour):
    records = images if isinstance(images, list) else []
    dictionaries = [image for image in records if isinstance(image, dict)]
    valid_build = isinstance(build, dict)
    layout_hash = build.get('layout_sha256', '') if valid_build else ''
    return '\n'.join([
        '### Simplestreams remote validation diagnostics',
        '',
        f'- Requested flavour: `{flavour}`',
        f'- Client JSON is a non-empty list: `{isinstance(images, list) and bool(images)}`',
        f'- Client image records: `{len(records)}`',
        f'- Records with fingerprint: `{sum(isinstance(image.get("fingerprint"), str) and bool(image["fingerprint"]) for image in dictionaries)}`',
        f'- Records with architecture: `{sum(isinstance(image.get("architecture"), str) and bool(image["architecture"]) for image in dictionaries)}`',
        f'- Portal schema valid: `{valid_build and build.get("schema") == 1}`',
        f'- Portal flavour matches: `{valid_build and build.get("flavour") == flavour}`',
        f'- Portal product count: `{build.get("products", 0) if valid_build else 0}`',
        f'- Portal layout hash valid: `{isinstance(layout_hash, str) and bool(SHA256.fullmatch(layout_hash))}`',
        '',
    ])


def report(text):
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as output:
            output.write(text)
    else:
        print(text, end='')


def validate(images, build, flavour):
    if not isinstance(images, list) or not images:
        raise ValueError('published Simplestreams source returned no images')
    malformed = []
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            malformed.append(str(index))
            continue
        if not isinstance(image.get('fingerprint'), str) or not image['fingerprint']:
            malformed.append(str(index))
        if not isinstance(image.get('architecture'), str) or not image['architecture']:
            malformed.append(str(index))
    if malformed:
        raise ValueError('published Simplestreams source returned malformed images at indexes ' + ','.join(malformed[:10]))
    if not isinstance(build, dict) or build.get('schema') != 1 or build.get('flavour') != flavour:
        raise ValueError('published image portal identity does not match the requested flavour')
    if not isinstance(build.get('products'), int) or build['products'] <= 0:
        raise ValueError('published image portal contains no products')
    if not isinstance(build.get('layout_sha256'), str) or not SHA256.fullmatch(build['layout_sha256']):
        raise ValueError('published image portal layout identity is invalid')
    return len(images)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--flavour', choices=['incus', 'lxd'], required=True)
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    build = json.loads(args.build.read_text())
    report(diagnostic(images, build, args.flavour))
    count = validate(images, build, args.flavour)
    print('Anonymous Simplestreams client validated', count, 'images; portal products', build['products'])


if __name__ == '__main__':
    main()
