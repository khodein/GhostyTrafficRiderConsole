#!/usr/bin/env bash
# Deploys Shadowsocks-libev + v2ray-plugin (TLS/websocket) behind a Let's Encrypt
# certificate on a fresh Ubuntu 22.04/24.04 x86_64 VPS, with automated cert renewal.
# Run as root on the target VPS. Idempotent: safe to re-run.
#
# Usage: SERVER_IP=1.2.3.4 [PROXY_PORT=8443] ./install.sh
# PROXY_PORT is only consulted on the very first install; once proxy.env
# exists the port is fixed until the config is removed and reinstalled.
set -euo pipefail

: "${SERVER_IP:?Set SERVER_IP to the VPS public IPv4 address}"

PROVIDER="shadowsocks-xray"
DOMAIN="${SERVER_IP}.sslip.io"
PROXY_DIR="/opt/proxy/${PROVIDER}"
CERT_LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"
ENV_FILE="${PROXY_DIR}/proxy.env"
HOOK_DIR=/etc/letsencrypt/renewal-hooks/deploy
HOOK_SCRIPT="${HOOK_DIR}/reload-shadowsocks.sh"

log() { printf '\n>>> %s\n' "$1"; }

log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban certbot curl openssl

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

mkdir -p "${PROXY_DIR}/certs" "${HOOK_DIR}"

log "Generating (or reusing) Shadowsocks credentials"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  SS_PORT="${PROXY_PORT:-$(( (RANDOM % 50000) + 10000 ))}"
  SS_PASSWORD=$(openssl rand -base64 24)
  cat > "${ENV_FILE}" <<EOF
SS_PORT=${SS_PORT}
SS_PASSWORD=${SS_PASSWORD}
EOF
fi
chmod 600 "${ENV_FILE}"

log "Configuring UFW"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow "${SS_PORT}"/tcp
ufw allow "${SS_PORT}"/udp
ufw --force enable

log "Enabling fail2ban for sshd"
systemctl enable --now fail2ban

log "Installing certbot renewal deploy-hook (runs only on actual renewal)"
install -m 0755 "$(dirname "$0")/renew-hook.sh" "${HOOK_SCRIPT}"
bash -n "${HOOK_SCRIPT}"

log "Issuing certificate for ${DOMAIN} (standalone HTTP-01, port 80)"
if [[ ! -d "${CERT_LIVE_DIR}" ]]; then
  certbot certonly --standalone --non-interactive --agree-tos \
    --register-unsafely-without-email \
    -d "${DOMAIN}"
else
  log "Certificate already exists, skipping initial issuance"
fi

log "Seeding proxy certs from the current certificate (deploy-hooks only fire on renewal)"
DOMAIN="${DOMAIN}" "${HOOK_SCRIPT}" --seed-only

log "Writing Shadowsocks-libev config"
# shellcheck disable=SC1090
source "${ENV_FILE}"
cat > "${PROXY_DIR}/config.json" <<EOF
{
  "server": "0.0.0.0",
  "server_port": ${SS_PORT},
  "password": "${SS_PASSWORD}",
  "method": "chacha20-ietf-poly1305",
  "mode": "tcp_and_udp",
  "plugin": "v2ray-plugin",
  "plugin_opts": "server;host=${DOMAIN};path=/ws;tls;cert=/certs/fullchain.pem;key=/certs/privkey.pem"
}
EOF

log "(Re)starting the Shadowsocks container"
docker rm -f "${PROVIDER}" >/dev/null 2>&1 || true
docker run -d \
  --restart unless-stopped \
  --network host \
  -v "${PROXY_DIR}/config.json:/etc/shadowsocks-libev/config.json:ro" \
  -v "${PROXY_DIR}/certs:/certs:ro" \
  --name "${PROVIDER}" teddysun/shadowsocks-libev:latest

log "Enabling certbot's persistent renewal timer"
systemctl enable --now certbot.timer

log "Validating renewal (dry run, no real request sent to Let's Encrypt)"
certbot renew --dry-run

TIMER_ENABLED=$(systemctl is-enabled certbot.timer)
TIMER_ACTIVE=$(systemctl is-active certbot.timer)
CERT_EXPIRY=$(openssl x509 -enddate -noout -in "${CERT_LIVE_DIR}/fullchain.pem" | cut -d= -f2)

cat > "${PROXY_DIR}/client-info.json" <<EOF
{
  "provider": "${PROVIDER}",
  "ip": "${SERVER_IP}",
  "domain": "${DOMAIN}",
  "port": ${SS_PORT},
  "password": "${SS_PASSWORD}",
  "method": "chacha20-ietf-poly1305",
  "cert_expiry": "${CERT_EXPIRY}"
}
EOF
chmod 600 "${PROXY_DIR}/client-info.json"

log "Setup report"
cat <<EOF
Renewal schedule : systemd certbot.timer (enabled=${TIMER_ENABLED}, active=${TIMER_ACTIVE}), checks twice daily
Reload mechanism : ${HOOK_SCRIPT} (certbot deploy-hook, fires only on actual renewal)
Certificate      : ${DOMAIN}
Expires (notAfter): ${CERT_EXPIRY}
Dry-run renewal  : OK
Client info      : ${PROXY_DIR}/client-info.json (fetch this file to generate the Clash Verge profile)
EOF
