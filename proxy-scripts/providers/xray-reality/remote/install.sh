#!/usr/bin/env bash
# Deploys Xray-core (VLESS + TCP + Reality) on a fresh Ubuntu 22.04/24.04
# x86_64 VPS. Adapted from AmneziaVPN's server_scripts/xray container
# (Dockerfile/start.sh, uploaded alongside this script) - the server-side
# inbound config (server.json) and key generation are our own, since
# Amnezia's desktop app builds those client-side in C++ and doesn't ship
# them as shell scripts.
#
# Reality needs no certificate of its own: unauthenticated probes get
# transparently proxied to the real $XRAY_SITE_NAME, so this provider has
# no certbot/renewal story (unlike shadowsocks-xray).
#
# Usage: SERVER_IP=1.2.3.4 [PROXY_PORT=443] [XRAY_SITE_NAME=www.apple.com] ./install.sh
# PROXY_PORT is only consulted on the very first install; once proxy.env
# exists the port is fixed until the config is removed and reinstalled.
# Note: Reality's camouflage works best on 443 (looks like normal HTTPS) -
# a random high port still works, but is easier for DPI to flag as unusual.
set -euo pipefail

: "${SERVER_IP:?Set SERVER_IP to the VPS public IPv4 address}"

PROVIDER="xray-reality"
PROXY_DIR="/opt/proxy/${PROVIDER}"
BUILD_DIR="${PROXY_DIR}/build"
ENV_FILE="${PROXY_DIR}/proxy.env"
IMAGE_NAME="xray-reality"
CONTAINER_NAME="xray-reality"

log() { printf '\n>>> %s\n' "$1"; }

log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban curl openssl python3

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

mkdir -p "${PROXY_DIR}" "${BUILD_DIR}"
cp "$(dirname "$0")/Dockerfile" "$(dirname "$0")/start.sh" "${BUILD_DIR}/"

log "Generating (or reusing) Reality parameters"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  XRAY_PORT="${PROXY_PORT:-$(( (RANDOM % 50000) + 10000 ))}"
  # The camouflage site must support TLS 1.3 + h2 and have a SMALL handshake:
  # Reality buffers the site's whole server flight (~8 KB), and
  # www.microsoft.com (8.2 KB certificate + post-quantum ServerHello) overflows
  # it - authenticated clients then get "handshake did not complete".
  XRAY_SITE="${XRAY_SITE_NAME:-www.apple.com}"
  cat > "${ENV_FILE}" <<EOF
XRAY_PORT=${XRAY_PORT}
XRAY_SITE=${XRAY_SITE}
EOF
fi
chmod 600 "${ENV_FILE}"
# shellcheck disable=SC1090
source "${ENV_FILE}"

log "Building the Xray-core image"
docker build -t "${IMAGE_NAME}:latest" "${BUILD_DIR}"

if [[ ! -f "${ENV_FILE}.keys" ]]; then
  log "Generating client id, keypair and short id (one-time)"
  XRAY_CLIENT_ID=$(docker run --rm --entrypoint xray "${IMAGE_NAME}:latest" uuid)
  XRAY_SHORT_ID=$(openssl rand -hex 8)

  KEYPAIR=$(docker run --rm --entrypoint xray "${IMAGE_NAME}:latest" x25519)
  XRAY_PRIVATE_KEY=$(printf '%s\n' "${KEYPAIR}" | sed -n 's/.*[Pp]rivate[ ]*[Kk]ey:[[:space:]]*//p' | head -1 | tr -d ' ')
  XRAY_PUBLIC_KEY=$(printf '%s\n' "${KEYPAIR}" | sed -n 's/.*(PublicKey):[[:space:]]*//p' | head -1 | tr -d ' ')
  if [[ -z "${XRAY_PUBLIC_KEY}" ]]; then
    XRAY_PUBLIC_KEY=$(printf '%s\n' "${KEYPAIR}" | sed -n 's/.*[Pp]ublic[ ]*[Kk]ey:[[:space:]]*//p' | head -1 | tr -d ' ')
  fi

  cat > "${ENV_FILE}.keys" <<EOF
XRAY_CLIENT_ID=${XRAY_CLIENT_ID}
XRAY_SHORT_ID=${XRAY_SHORT_ID}
XRAY_PRIVATE_KEY=${XRAY_PRIVATE_KEY}
XRAY_PUBLIC_KEY=${XRAY_PUBLIC_KEY}
EOF
  chmod 600 "${ENV_FILE}.keys"
else
  log "Reusing existing client id / keypair"
fi
# shellcheck disable=SC1090
source "${ENV_FILE}.keys"

log "Writing Xray server inbound config (VLESS + TCP + Reality) and client-info.json"
# clients.py builds server.json from clients.json (one UUID per device; the
# very first run turns the pre-existing client into the "default" device).
SERVER_IP="${SERVER_IP}" PROXY_STATE_DIR="${PROXY_DIR}" python3 "$(dirname "$0")/clients.py" render

log "Configuring UFW"
ufw allow OpenSSH
ufw allow "${XRAY_PORT}"/tcp
ufw allow "${XRAY_PORT}"/udp
ufw --force enable

log "Enabling fail2ban for sshd"
systemctl enable --now fail2ban

log "(Re)starting the Xray-core container"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
docker run -d \
  --privileged \
  --cap-add=NET_ADMIN \
  --restart unless-stopped \
  -p "${XRAY_PORT}:${XRAY_PORT}/tcp" \
  -p "${XRAY_PORT}:${XRAY_PORT}/udp" \
  -e "XRAY_SERVER_PORT=${XRAY_PORT}" \
  -v "${PROXY_DIR}/server.json:/opt/amnezia/xray/server.json:ro" \
  --name "${CONTAINER_NAME}" "${IMAGE_NAME}:latest"

log "Setup report"
cat <<EOF
Protocol         : VLESS + TCP + Reality (Xray-core ${IMAGE_NAME})
Port             : ${XRAY_PORT}
Camouflage site  : ${XRAY_SITE} (Reality dest - no certificate of our own, nothing to renew)
Devices          : manage with clients.sh add|remove|list (one UUID per device)
Client info      : ${PROXY_DIR}/client-info.json (fetch this file to generate the client profile)
EOF
