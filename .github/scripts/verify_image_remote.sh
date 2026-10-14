#!/usr/bin/env bash
set -euo pipefail
flavour=${1:?incus or lxd required}
[[ "$flavour" == incus || "$flavour" == lxd ]] || exit 1
source .github/scripts/ci_network.sh
ci_retry sudo apt-get update -y
ci_retry sudo apt-get install -y --no-install-recommends incus-client
remote="${flavour}-published"
url="https://${flavour}images.spiritlhl.net"
incus remote add "$remote" "$url" --protocol=simplestreams --public
trap 'incus remote remove "$remote" >/dev/null 2>&1 || true' EXIT
ci_retry incus image list "$remote:" --format=json > "$RUNNER_TEMP/remote-images.json"
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 60 --retry 3 \
    "$url/image-portal-build.json" -o "$RUNNER_TEMP/live-portal-build.json"
python3 .github/scripts/validate_image_remote.py \
    --images "$RUNNER_TEMP/remote-images.json" \
    --build "$RUNNER_TEMP/live-portal-build.json" \
    --flavour "$flavour"
