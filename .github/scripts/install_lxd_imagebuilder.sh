#!/usr/bin/env bash
set -euo pipefail
commit=d058e8c44b1684d4537f57f139cde81fa6226548
digest=21f7e83390eec82a4182b90f73e7414ed3b725115e2421f02af21c4ca1315fbf
task_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lxd-imagebuilder.XXXXXXXX")
trap 'rm -rf -- "$task_dir"' EXIT
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 --retry 3 --retry-max-time 240 \
    "https://codeload.github.com/oneclickvirt/lxd-imagebuilder/tar.gz/${commit}" -o "$task_dir/source.tar.gz"
printf '%s  %s\n' "$digest" "$task_dir/source.tar.gz" | sha256sum --check --status
tar -xzf "$task_dir/source.tar.gz" -C "$task_dir"
python3 - "$task_dir/lxd-imagebuilder-${commit}/sources/centos-http.go" <<'PYCOMPAT'
from pathlib import Path
import sys
path=Path(sys.argv[1]);source=path.read_text()
for before,after in [
    ('if s.definition.Image.Release == "9-Stream" {','if s.definition.Image.Release == "9-Stream" || s.definition.Image.Release == "10-Stream" {'),
    ('if release == "9-Stream" {','if release == "9-Stream" || release == "10-Stream" {')]:
    if source.count(before)!=1:raise SystemExit('CentOS Stream compatibility patch did not match the verified builder')
    source=source.replace(before,after)
path.write_text(source)
PYCOMPAT
sudo apt-get update
sudo apt-get install -y build-essential libacl1-dev libattr1-dev debootstrap rsync gpg squashfs-tools xz-utils umoci btrfs-progs dosfstools qemu-utils parted
(
    cd "$task_dir/lxd-imagebuilder-${commit}"
    export GOPROXY='https://proxy.golang.org|direct'
    go test -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp ./sources
    go build -trimpath -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp \
        -o "$task_dir/lxd-imagebuilder" ./lxd-imagebuilder
)
sudo install -m 0755 "$task_dir/lxd-imagebuilder" /usr/local/bin/lxd-imagebuilder
lxd-imagebuilder --version
