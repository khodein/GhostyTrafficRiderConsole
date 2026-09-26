#!/usr/bin/env bash
# Dispatches to providers/<name>/generate-config.sh based on the "provider"
# field that provider's remote/install.sh recorded in client-info.json.
# This script itself never changes when a new provider is added.
#
# Usage: ./generate-config.sh <client-info.json> [output]
set -euo pipefail

INFO_FILE="${1:?Usage: generate-config.sh <client-info.json> [output]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROVIDER=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['provider'])" "${INFO_FILE}")
PROVIDER_SCRIPT="${SCRIPT_DIR}/providers/${PROVIDER}/generate-config.sh"

if [[ ! -x "${PROVIDER_SCRIPT}" ]]; then
  echo "No generate-config.sh for provider '${PROVIDER}' (expected ${PROVIDER_SCRIPT})" >&2
  exit 1
fi

exec "${PROVIDER_SCRIPT}" "$@"
