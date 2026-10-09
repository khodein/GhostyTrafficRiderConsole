#!/usr/bin/env bash
# Builds a Clash Verge (mihomo) YAML profile for the VLESS+Reality server,
# from the values produced by remote/install.sh (the YAML uses the first
# device). Also prints and saves a vless:// share link for EVERY device in
# client-info.json ("clients"), for clients that import links (Hiddify, ...).
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

OUTPUT="${2:-${PROXY_SCRIPTS_DIR}/output/xray-reality/${IP}.yaml}"
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
LINK_FILE="${OUTPUT%.yaml}.txt"
# One "name<TAB>uuid<TAB>url-encoded title" line per device. The title is the
# profile name shown by the client: "<SERVER_LABEL> · <device>" (SERVER_LABEL is
# the server's name in the console), or just the device name without a label.
# Older client-info.json without a "clients" list has the single device "default".
DEVICES=$(SERVER_LABEL="${SERVER_LABEL:-}" python3 - "${INFO_FILE}" <<'PY'
import json, os, sys
from urllib.parse import quote

info = json.load(open(sys.argv[1]))
label = os.environ.get("SERVER_LABEL", "")
for c in info.get("clients") or [{"name": "default", "uuid": info["uuid"]}]:
    title = f"{label} \u00b7 {c['name']}" if label else c["name"]
    print(f"{c['name']}\t{c['uuid']}\t{quote(title, safe='')}")
PY
)

: > "${LINK_FILE}"
while IFS=$'\t' read -r DEVICE_NAME DEVICE_UUID DEVICE_TITLE; do
  LINK="vless://${DEVICE_UUID}@${IP}:${PORT}?security=reality&sni=${SITE_NAME}&fp=${FINGERPRINT}&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&type=tcp&flow=${FLOW}&encryption=none#${DEVICE_TITLE}"
  printf '%s\n' "${LINK}" >> "${LINK_FILE}"
  echo "[${DEVICE_NAME}]"
  echo "${LINK}"
done <<< "${DEVICES}"

echo "Share links written to: ${LINK_FILE}"
