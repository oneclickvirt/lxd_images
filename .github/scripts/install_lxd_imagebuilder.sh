#!/usr/bin/env bash
set -euo pipefail
task_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lxd-imagebuilder.XXXXXXXX")
trap 'rm -rf -- "$task_dir"' EXIT
source .github/scripts/ci_network.sh
export GOPROXY='https://proxy.golang.org|direct'
export GOTOOLCHAIN=auto
ci_retry sudo apt-get update
ci_retry sudo apt-get install -y build-essential libacl1-dev libattr1-dev debootstrap rsync gpg squashfs-tools xz-utils umoci btrfs-progs dosfstools qemu-utils parted
build_source() {
    local repository=$1 commit=$2 digest=${3:-}
    local folder="$task_dir/source-${commit}"
    mkdir -p "$folder"
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 --retry 3 --retry-max-time 240 \
        "https://codeload.github.com/${repository}/tar.gz/${commit}" -o "$folder/source.tar.gz" || return 1
    if [[ -n "$digest" ]]; then printf '%s  %s\n' "$digest" "$folder/source.tar.gz" | sha256sum --check --status || return 1; fi
    tar -xzf "$folder/source.tar.gz" -C "$folder" --strip-components=1 || return 1
    python3 - "$folder/sources/centos-http.go" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]); source = path.read_text()
# ISO and bootstrap repository mirrors are independent. Preserve GPG checks.
for mirror in ['https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/',
               'https://mirror.xenyth.net/centos-stream/']:
    source = source.replace(mirror, 'https://mirror.stream.centos.org/')
for before, after in [
    ('if s.definition.Image.Release == "9-Stream" {', 'if s.definition.Image.Release == "9-Stream" || s.definition.Image.Release == "10-Stream" {'),
    ('if release == "9-Stream" {', 'if release == "9-Stream" || release == "10-Stream" {')]:
    source = source.replace(before, after)
path.write_text(source)
PY
    [[ $? == 0 ]] || return 1
    python3 .github/scripts/patch_lxd_builder.py "$folder" || return 1
    python3 .github/scripts/patch_container_labels.py "$folder" || return 1
    (
        cd "$folder"
        timeout --kill-after=30s 900s go test -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp ./sources ./shared ./generators &&
        timeout --kill-after=30s 600s go build -trimpath -tags=containers_image_storage_stub,containers_image_docker_daemon_stub,containers_image_openpgp \
            -o "$task_dir/lxd-imagebuilder" ./lxd-imagebuilder
    ) || return 1
    sudo install -m 0755 "$task_dir/lxd-imagebuilder" /usr/local/bin/lxd-imagebuilder || return 1
    printf '{"repository":"%s","commit":"%s","fallback":%s}\n' "$repository" "$commit" "$builder_fallback" > "$RUNNER_TEMP/image-builder-source.json"
}
latest=$(curl --fail --silent --show-error --location --connect-timeout 15 --max-time 60 --retry 2 \
    https://api.github.com/repos/canonical/lxd-imagebuilder/commits/main | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])') || latest=''
builder_fallback=false
if [[ "$latest" =~ ^[0-9a-f]{40}$ ]] && build_source canonical/lxd-imagebuilder "$latest"; then
    echo "Validated latest upstream image builder: $latest"
else
    builder_fallback=true
    echo '::notice::Latest upstream image builder unavailable; using the verified compatible builder.'
    build_source oneclickvirt/lxd-imagebuilder d058e8c44b1684d4537f57f139cde81fa6226548 21f7e83390eec82a4182b90f73e7414ed3b725115e2421f02af21c4ca1315fbf
    # The fallback predates string VM sizes. Preserve their exact byte value.
    "$RUNNER_TEMP/image-definition-check/bin/python" - <<'PY'
from pathlib import Path
import re
from sys import path
path.insert(0, '.github/scripts')
from append_image_actions import serialize
from verify_image_definitions import verify
units = {'B':1,'KiB':1024,'MiB':1024**2,'GiB':1024**3,'kB':1000,'MB':1000**2,'GB':1000**3}
for filename in Path('images_yaml').glob('*.yaml'):
    document = verify(filename.read_text())
    vm = document.get('targets', {}).get('lxd', {}).get('vm', {})
    if isinstance(vm.get('size'), str):
        match = re.fullmatch(r'([0-9]+)(B|KiB|MiB|GiB|kB|MB|GB)', vm['size'])
        if not match: raise ValueError('unsupported fallback VM size')
        vm['size'] = int(match[1]) * units[match[2]]
        filename.write_text(serialize(document))
PY
fi
lxd-imagebuilder --version
