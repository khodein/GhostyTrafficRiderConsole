#!/usr/bin/env bash
# Dispatches to providers/<name>/verify.sh based on the "provider" field
# that provider's remote/install.sh recorded in client-info.json.
# This script itself never changes when a new provider is added.
#
# Usage: ./verify.sh <client-info.json>
set -euo pipefail

INFO_FILE="${1:?Usage: verify.sh <client-info.json>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROVIDER=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['provider'])" "${INFO_FILE}")
PROVIDER_SCRIPT="${SCRIPT_DIR}/providers/${PROVIDER}/verify.sh"

if [[ ! -x "${PROVIDER_SCRIPT}" ]]; then
  echo "No verify.sh for provider '${PROVIDER}' (expected ${PROVIDER_SCRIPT})" >&2
  exit 1
fi

exec "${PROVIDER_SCRIPT}" "$@"
