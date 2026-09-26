#!/usr/bin/env bash
# certbot deploy-hook: copies the fresh certificate into the proxy's cert
# directory and restarts the Shadowsocks container so it picks it up.
#
# Certbot only executes deploy-hooks after an actual renewal, so the
# container is never restarted on a no-op "certbot renew" run.
#
# Also usable manually once, right after the initial `certbot certonly`,
# via: DOMAIN=<domain> ./renew-hook.sh --seed-only
set -euo pipefail

PROXY_DIR=/opt/proxy/shadowsocks-xray
CONTAINER_NAME=shadowsocks-xray

if [[ "${1:-}" == "--seed-only" ]]; then
  : "${DOMAIN:?Set DOMAIN when calling with --seed-only}"
  LINEAGE="/etc/letsencrypt/live/${DOMAIN}"
else
  : "${RENEWED_LINEAGE:?This script must be run by certbot as a deploy-hook}"
  LINEAGE="${RENEWED_LINEAGE}"
fi

install -m 0644 "${LINEAGE}/fullchain.pem" "${PROXY_DIR}/certs/fullchain.pem"
install -m 0600 "${LINEAGE}/privkey.pem" "${PROXY_DIR}/certs/privkey.pem"

if [[ "${1:-}" != "--seed-only" ]]; then
  docker restart "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi
