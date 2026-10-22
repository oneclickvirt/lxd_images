#!/bin/bash
set -euo pipefail

# The CLI's default preparation timeout is as long as the old step budget,
# so a stalled Netlify diff used to prevent every configured retry.
for attempt in 1 2 3; do
    if timeout --kill-after=30s 8m npm exec --yes --package=netlify-cli@27.12.1 -- netlify deploy \
        --dir ./build --no-build --prod --site "$NETLIFY_SITE_ID" --auth "$NETLIFY_AUTH_TOKEN" \
        --timeout 360 --message "${GITHUB_REPOSITORY}@${GITHUB_SHA}"; then
        exit 0
    else
        status=$?
    fi
    echo "Netlify deploy attempt $attempt failed (exit $status)." >&2
    if [[ "$attempt" -lt 3 ]]; then
        sleep "$((attempt * 10))"
    fi
done

echo 'Netlify deployment failed after 3 bounded attempts; the existing production site remains active.' >&2
exit "$status"
