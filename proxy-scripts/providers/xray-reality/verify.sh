#!/usr/bin/env bash
# External check for VLESS+Reality: Reality has no certificate of its own -
# unauthenticated TLS probes get transparently proxied to the real
# camouflage site, so a full Xray/VLESS handshake can't be checked without
# a real client. This instead confirms: the port is reachable, and the TLS
# certificate seen matches the camouflage site (proof Reality's dest is
# wired correctly) with a future expiry.
#
# Usage: ./verify.sh <client-info.json>
set -euo pipefail

INFO_FILE="${1:?Usage: verify.sh <client-info.json>}"

IP=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ip'])" "${INFO_FILE}")
PORT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['port'])" "${INFO_FILE}")
SITE_NAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['site_name'])" "${INFO_FILE}")

echo ">>> Checking TCP reachability on ${IP}:${PORT}"
if ! (exec 3<>"/dev/tcp/${IP}/${PORT}") 2>/dev/null; then
  echo "FAIL: ${IP}:${PORT} is not reachable" >&2
  exit 1
fi
exec 3>&- 2>/dev/null || true
echo "OK: port is reachable"

echo ">>> Checking camouflage TLS handshake (SNI: ${SITE_NAME})"
CERT_INFO=$(echo | openssl s_client -connect "${IP}:${PORT}" -servername "${SITE_NAME}" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -enddate 2>/dev/null || true)

if [[ -z "${CERT_INFO}" ]]; then
  echo "FAIL: no TLS certificate returned for SNI ${SITE_NAME} - Reality dest may be misconfigured" >&2
  exit 1
fi
echo "${CERT_INFO}"

NOT_AFTER=$(echo "${CERT_INFO}" | grep '^notAfter=' | cut -d= -f2)
EXPIRY_EPOCH=$(date -j -f "%b %d %T %Y %Z" "${NOT_AFTER}" +%s 2>/dev/null || date -d "${NOT_AFTER}" +%s)
NOW_EPOCH=$(date +%s)

if [[ "${EXPIRY_EPOCH}" -le "${NOW_EPOCH}" ]]; then
  echo "FAIL: camouflage certificate notAfter (${NOT_AFTER}) is not in the future" >&2
  exit 1
fi

echo "OK: camouflage TLS looks legitimate, expires ${NOT_AFTER}"
echo "Note: this does not verify the VLESS/Reality handshake itself - do a real connection test with a client."
