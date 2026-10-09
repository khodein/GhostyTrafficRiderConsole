#!/usr/bin/env bash
# Deploys an MTProto proxy for Telegram (FakeTLS mode) on a fresh Ubuntu
# 22.04/24.04 VPS (Dockerfile/start.sh are uploaded alongside this script).
#
# FakeTLS: the client link carries the camouflage domain inside the secret
# (ee + secret + hex(domain)), so DPI sees a TLS handshake to that domain.
# There is no certificate of our own - nothing to renew.
#
# Usage: SERVER_IP=1.2.3.4 [PROXY_PORT=443] [MTPROXY_TLS_DOMAIN=www.microsoft.com] ./install.sh
# PROXY_PORT is only consulted on the very first install; once proxy.env
# exists the port is fixed until the config is removed and reinstalled.
# FakeTLS looks most natural on 443.
set -euo pipefail

: "${SERVER_IP:?Set SERVER_IP to the VPS public IPv4 address}"

PROVIDER="mtproxy"
PROXY_DIR="/opt/proxy/${PROVIDER}"
BUILD_DIR="${PROXY_DIR}/build"
DATA_DIR="${PROXY_DIR}/data"
ENV_FILE="${PROXY_DIR}/proxy.env"
IMAGE_NAME="mtproxy"
CONTAINER_NAME="mtproxy"

log() { printf '\n>>> %s\n' "$1"; }

log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban curl openssl

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

mkdir -p "${PROXY_DIR}" "${BUILD_DIR}" "${DATA_DIR}"
cp "$(dirname "$0")/Dockerfile" "$(dirname "$0")/start.sh" "${BUILD_DIR}/"

log "Generating (or reusing) proxy parameters"
if [[ ! -f "${ENV_FILE}" ]]; then
  MTPROXY_PORT="${PROXY_PORT:-$(( (RANDOM % 50000) + 10000 ))}"
  MTPROXY_TLS_DOMAIN="${MTPROXY_TLS_DOMAIN:-www.microsoft.com}"
  MTPROXY_SECRET=$(openssl rand -hex 16)
  cat > "${ENV_FILE}" <<EOF2
MTPROXY_PORT=${MTPROXY_PORT}
MTPROXY_TLS_DOMAIN=${MTPROXY_TLS_DOMAIN}
MTPROXY_SECRET=${MTPROXY_SECRET}
EOF2
else
  log "Reusing existing port / domain / secret"
fi
chmod 600 "${ENV_FILE}"
# shellcheck disable=SC1090
source "${ENV_FILE}"

log "Downloading Telegram proxy config"
curl -fsS https://core.telegram.org/getProxySecret -o "${DATA_DIR}/proxy-secret"
curl -fsS https://core.telegram.org/getProxyConfig -o "${DATA_DIR}/proxy-multi.conf"
printf '%s' "${MTPROXY_SECRET}" > "${DATA_DIR}/secret"
chmod 600 "${DATA_DIR}/secret"

log "Building the MTProxy image"
docker build -t "${IMAGE_NAME}:latest" "${BUILD_DIR}"

log "Configuring UFW"
ufw allow OpenSSH
ufw allow "${MTPROXY_PORT}"/tcp
ufw --force enable

log "Enabling fail2ban for sshd"
systemctl enable --now fail2ban

log "(Re)starting the MTProxy container"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
docker run -d \
  --restart unless-stopped \
  -p "${MTPROXY_PORT}:${MTPROXY_PORT}/tcp" \
  -e "MTPROXY_PORT=${MTPROXY_PORT}" \
  -e "MTPROXY_TLS_DOMAIN=${MTPROXY_TLS_DOMAIN}" \
  -e "MTPROXY_PUBLIC_IP=${SERVER_IP}" \
  -v "${DATA_DIR}:/data" \
  --name "${CONTAINER_NAME}" "${IMAGE_NAME}:latest"

DOMAIN_HEX=$(printf '%s' "${MTPROXY_TLS_DOMAIN}" | od -A n -t x1 | tr -d ' \n')
FAKETLS_SECRET="ee${MTPROXY_SECRET}${DOMAIN_HEX}"

cat > "${PROXY_DIR}/client-info.json" <<EOF2
{
  "provider": "${PROVIDER}",
  "ip": "${SERVER_IP}",
  "port": ${MTPROXY_PORT},
  "secret": "${MTPROXY_SECRET}",
  "tls_domain": "${MTPROXY_TLS_DOMAIN}",
  "faketls_secret": "${FAKETLS_SECRET}"
}
EOF2
chmod 600 "${PROXY_DIR}/client-info.json"

log "Setup report"
cat <<EOF2
Protocol         : MTProto proxy for Telegram, FakeTLS
Port             : ${MTPROXY_PORT}
Camouflage domain: ${MTPROXY_TLS_DOMAIN} (no certificate of our own - nothing to renew)
Client info      : ${PROXY_DIR}/client-info.json (fetch this file to generate the connection link)
EOF2
