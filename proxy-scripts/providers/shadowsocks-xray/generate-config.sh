#!/usr/bin/env bash
# Builds a Clash Verge YAML profile from templates/clash-config.yaml.tmpl,
# filled in with the values produced by remote/install.sh.
#
# Usage: ./generate-config.sh <client-info.json> [output.yaml]
set -euo pipefail

INFO_FILE="${1:?Usage: generate-config.sh <client-info.json> [output.yaml]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/templates/clash-config.yaml.tmpl"
PROXY_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IP=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ip'])" "${INFO_FILE}")
DOMAIN=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['domain'])" "${INFO_FILE}")
PORT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['port'])" "${INFO_FILE}")
PASSWORD=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['password'])" "${INFO_FILE}")

OUTPUT="${2:-${PROXY_SCRIPTS_DIR}/output/shadowsocks-xray/${IP}.yaml}"
mkdir -p "$(dirname "${OUTPUT}")"

sed \
  -e "s/__SERVER_IP__/${IP}/g" \
  -e "s/__SERVER_DOMAIN__/${DOMAIN}/g" \
  -e "s/__SERVER_PORT__/${PORT}/g" \
  -e "s#__SERVER_PASSWORD__#${PASSWORD}#g" \
  "${TEMPLATE}" > "${OUTPUT}"

echo "Clash Verge profile written to: ${OUTPUT}"
