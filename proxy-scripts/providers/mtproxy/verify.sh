#!/usr/bin/env bash
# External check for MTProxy FakeTLS: confirms the port is reachable and that
# a TLS ClientHello with the camouflage SNI gets a TLS answer. A full MTProto
# handshake can't be checked without Telegram - do a real connection test.
#
# Usage: ./verify.sh <client-info.json>
set -euo pipefail

INFO_FILE="${1:?Usage: verify.sh <client-info.json>}"

field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "${INFO_FILE}" "$1"; }

IP=$(field ip)
PORT=$(field port)
DOMAIN=$(field tls_domain)

echo ">>> Checking TCP reachability on ${IP}:${PORT}"
if ! (exec 3<>"/dev/tcp/${IP}/${PORT}") 2>/dev/null; then
  echo "FAIL: ${IP}:${PORT} is not reachable" >&2
  exit 1
fi
exec 3>&- 2>/dev/null || true
echo "OK: port is reachable"

echo ">>> Checking TLS answer (SNI: ${DOMAIN})"
if echo | openssl s_client -connect "${IP}:${PORT}" -servername "${DOMAIN}" 2>&1 | grep -qiE 'SSL handshake has read|BEGIN CERTIFICATE|Protocol *:'; then
  echo "OK: server answers a TLS handshake"
else
  echo "WARN: no TLS answer for SNI ${DOMAIN} (proxy may answer only valid MTProto clients)" >&2
fi

echo "Note: this does not verify the MTProto handshake itself - open the link in Telegram."
