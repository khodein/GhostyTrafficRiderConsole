#!/usr/bin/env bash
# Builds Telegram connection links (tg:// and https://t.me/) for the MTProxy
# server, from the values produced by remote/install.sh. Unlike the Clash
# providers there is no YAML profile - Telegram imports the link directly.
#
# Usage: ./generate-config.sh <client-info.json> [output.txt]
set -euo pipefail

INFO_FILE="${1:?Usage: generate-config.sh <client-info.json> [output.txt]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "${INFO_FILE}" "$1"; }

IP=$(field ip)
PORT=$(field port)
SECRET=$(field faketls_secret)

OUTPUT="${2:-${PROXY_SCRIPTS_DIR}/output/mtproxy-${IP}.txt}"
mkdir -p "$(dirname "${OUTPUT}")"

TG_LINK="tg://proxy?server=${IP}&port=${PORT}&secret=${SECRET}"
WEB_LINK="https://t.me/proxy?server=${IP}&port=${PORT}&secret=${SECRET}"

printf '%s\n%s\n' "${TG_LINK}" "${WEB_LINK}" > "${OUTPUT}"

echo "Links written to: ${OUTPUT}"
echo "Telegram key (tg://): ${TG_LINK}"
echo "Telegram key (t.me) : ${WEB_LINK}"
