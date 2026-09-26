#!/usr/bin/env bash
# Builds a Clash Verge (mihomo) YAML profile for the VLESS+Reality server,
# from the values produced by remote/install.sh. Also prints a vless://
# share link for clients that prefer that over a YAML profile.
#
# Usage: ./generate-config.sh <client-info.json> [output.yaml]
set -euo pipefail

INFO_FILE="${1:?Usage: generate-config.sh <client-info.json> [output.yaml]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/templates/clash-vless.yaml.tmpl"
PROXY_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "${INFO_FILE}" "$1"; }

IP=$(field ip)
PORT=$(field port)
UUID=$(field uuid)
PUBLIC_KEY=$(field public_key)
SHORT_ID=$(field short_id)
SITE_NAME=$(field site_name)
FLOW=$(field flow)
FINGERPRINT=$(field fingerprint)

OUTPUT="${2:-${PROXY_SCRIPTS_DIR}/output/xray-reality-${IP}.yaml}"
mkdir -p "$(dirname "${OUTPUT}")"

sed \
  -e "s/__SERVER_IP__/${IP}/g" \
  -e "s/__SERVER_PORT__/${PORT}/g" \
  -e "s#__CLIENT_UUID__#${UUID}#g" \
  -e "s#__PUBLIC_KEY__#${PUBLIC_KEY}#g" \
  -e "s#__SHORT_ID__#${SHORT_ID}#g" \
  -e "s/__SITE_NAME__/${SITE_NAME}/g" \
  -e "s/__FLOW__/${FLOW}/g" \
  -e "s/__FINGERPRINT__/${FINGERPRINT}/g" \
  "${TEMPLATE}" > "${OUTPUT}"

echo "Clash Verge profile written to: ${OUTPUT}"
echo "vless share link: vless://${UUID}@${IP}:${PORT}?security=reality&sni=${SITE_NAME}&fp=${FINGERPRINT}&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&type=tcp&flow=${FLOW}&encryption=none#MyServer"
