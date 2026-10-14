#!/usr/bin/env bash
set -euo pipefail
flavour=${1:?incus or lxd required}
[[ "$flavour" == incus || "$flavour" == lxd ]] || exit 1
source .github/scripts/ci_network.sh
summary_stage() {
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        printf '\n- Remote validation reached: `%s`\n' "$1" >> "$GITHUB_STEP_SUMMARY"
    fi
}
if [[ "$flavour" == lxd ]]; then
    # Incus deliberately ignores lxd.tar.xz metadata. Validate this source
    # with the same native client its consumers use.
    summary_stage 'installing the native LXD client'
    ci_retry sudo snap install lxd --channel=5.21/stable
    client=/snap/bin/lxc
else
    summary_stage 'installing the native Incus client'
    ci_retry sudo apt-get update -y
    ci_retry sudo apt-get install -y --no-install-recommends incus-client
    client=incus
fi
remote="${flavour}-published"
url="https://${flavour}images.spiritlhl.net"
summary_stage 'adding the anonymous Simplestreams remote'
ci_retry "$client" remote add "$remote" "$url" --protocol=simplestreams --public
trap '"$client" remote remove "$remote" >/dev/null 2>&1 || true' EXIT
summary_stage 'listing images through the native client'
ci_retry "$client" image list "$remote:" --format=json > "$RUNNER_TEMP/remote-images.json"
summary_stage 'reading the deployed portal identity'
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 60 --retry 3 \
    "$url/image-portal-build.json" -o "$RUNNER_TEMP/live-portal-build.json"
python3 .github/scripts/validate_image_remote.py \
    --images "$RUNNER_TEMP/remote-images.json" \
    --build "$RUNNER_TEMP/live-portal-build.json" \
    --flavour "$flavour"
