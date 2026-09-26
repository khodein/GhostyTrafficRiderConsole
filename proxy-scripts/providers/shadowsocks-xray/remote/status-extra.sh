#!/usr/bin/env bash
# Optional provider hook: extra status info beyond `docker ps`/`docker logs`,
# picked up by the TUI's Status/Logs action when present.
#
# Usage: SERVER_IP=1.2.3.4 ./status-extra.sh
set -euo pipefail

: "${SERVER_IP:?Set SERVER_IP to the VPS public IPv4 address}"
DOMAIN="${SERVER_IP}.sslip.io"

echo "--- certbot timer ---"
systemctl is-active certbot.timer 2>&1 || true
echo "--- certificate ---"
openssl x509 -enddate -noout -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" 2>&1 || true
