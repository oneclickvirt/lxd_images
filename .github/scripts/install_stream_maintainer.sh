#!/usr/bin/env bash
set -euo pipefail
flavour=${1:-lxd}
[[ "$flavour" == lxd || "$flavour" == incus ]] || exit 1
task_dir=$(mktemp -d "$RUNNER_TEMP/stream-maintainer.XXXXXXXX")
trap 'rm -rf -- "$task_dir"' EXIT
export GOPROXY='https://proxy.golang.org|direct'
build_source() {
    local repository=$1 commit=$2 digest=${3:-}
    local folder="$task_dir/source-${commit}"
    mkdir -p "$folder"
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 --retry 3 --retry-max-time 240 \
        "https://codeload.github.com/${repository}/tar.gz/${commit}" -o "$folder/source.tar.gz" || return 1
    if [[ -n "$digest" ]]; then printf '%s  %s\n' "$digest" "$folder/source.tar.gz" | sha256sum --check --status || return 1; fi
    tar -xzf "$folder/source.tar.gz" -C "$folder" --strip-components=1 || return 1
    if [[ "$flavour" == incus ]]; then
        python3 - "$folder/simplestream-maintainer/stream/stream.go" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]);text=path.read_text()
before='ItemTypeMetadata = "lxd.tar.xz"'
if text.count(before)!=1:raise SystemExit('Unsupported upstream metadata schema')
path.write_text(text.replace(before,'ItemTypeMetadata = "incus.tar.xz"'))
PY
        [[ $? == 0 ]] || return 1
    fi
    (
        cd "$folder"
        timeout --kill-after=30s 600s go test ./simplestream-maintainer/... &&
        timeout --kill-after=30s 600s go build -trimpath -o "$task_dir/simplestream-maintainer" ./simplestream-maintainer
    ) || return 1
    sudo install -m 0755 "$task_dir/simplestream-maintainer" /usr/local/bin/simplestream-maintainer || return 1
    printf '{"repository":"%s","commit":"%s","fallback":%s}\n' "$repository" "$commit" "$stream_fallback" > "$RUNNER_TEMP/stream-source.json"
}
latest=$(curl --fail --silent --show-error --location --connect-timeout 15 --max-time 60 --retry 2 \
    https://api.github.com/repos/canonical/lxd-imagebuilder/commits/main | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])') || latest=''
stream_fallback=false
if [[ "$latest" =~ ^[0-9a-f]{40}$ ]] && build_source canonical/lxd-imagebuilder "$latest"; then
    echo "Validated latest upstream Simplestreams builder: $latest"
else
    stream_fallback=true
    echo '::notice::Latest upstream builder unavailable; using the verified compatible builder.'
    build_source oneclickvirt/lxd-imagebuilder d058e8c44b1684d4537f57f139cde81fa6226548 21f7e83390eec82a4182b90f73e7414ed3b725115e2421f02af21c4ca1315fbf
fi
simplestream-maintainer --version
