#!/usr/bin/env bash
# External verification: connects to the VPS's TLS port from this machine
# (i.e. from outside the server) and checks the certificate chain and
# expiration date. Run after deploy.sh, or any time to re-check renewal.
#
# Usage: ./verify.sh <client-info.json>
set -euo pipefail

INFO_FILE="${1:?Usage: verify.sh <client-info.json>}"

IP=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ip'])" "${INFO_FILE}")
DOMAIN=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['domain'])" "${INFO_FILE}")
PORT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['port'])" "${INFO_FILE}")

echo ">>> Checking TLS chain on ${IP}:${PORT} (SNI: ${DOMAIN})"

CERT_INFO=$(echo | openssl s_client -connect "${IP}:${PORT}" -servername "${DOMAIN}" \
  -verify_return_error 2>/dev/null | openssl x509 -noout -subject -issuer -enddate)

echo "${CERT_INFO}"

NOT_AFTER=$(echo "${CERT_INFO}" | grep '^notAfter=' | cut -d= -f2)
EXPIRY_EPOCH=$(date -j -f "%b %d %T %Y %Z" "${NOT_AFTER}" +%s 2>/dev/null \
  || date -d "${NOT_AFTER}" +%s)
NOW_EPOCH=$(date +%s)

if [[ "${EXPIRY_EPOCH}" -le "${NOW_EPOCH}" ]]; then
  echo "FAIL: certificate notAfter (${NOT_AFTER}) is not in the future" >&2
  exit 1
fi

echo "OK: certificate verified, expires ${NOT_AFTER} (future date confirmed)"
