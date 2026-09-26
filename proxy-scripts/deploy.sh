#!/usr/bin/env bash
# Deploys any proxy/VPN provider under providers/<name>/ onto a VPS over SSH,
# then generates a ready-to-import client profile locally.
#
# Usage:
#   ./deploy.sh --provider shadowsocks-xray --host <VPS_IP> \
#     [--user root] [--ssh-port 22] [--key ~/.ssh/id_ed25519] [--port 8443]
#
# --port sets the port the proxy service itself listens on (not the SSH
# port). Only consulted on the very first install for a given server -
# omit it to get a random port in 10000-60000.
#
# Auth: uses your normal ssh/scp (agent, key, or interactive password prompt).
# No credentials are stored by this script.
#
# Provider contract (see providers/<name>/):
#   remote/install.sh    - entrypoint run on the VPS as `SERVER_IP=<host> install.sh`.
#                           Must be idempotent and must write
#                           /opt/proxy/<name>/client-info.json (JSON, with a
#                           "provider": "<name>" field).
#   remote/*              - any other files the provider needs on the VPS;
#                           everything in remote/ is uploaded alongside install.sh.
#   generate-config.sh    - <client-info.json> [output] -> writes a client profile.
#   verify.sh              - <client-info.json> -> external sanity check, exits
#                           non-zero on failure.
# The top-level generate-config.sh/verify.sh dispatch to these based on the
# "provider" field, so this script and they stay the same for every provider.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_USER="root"
SSH_PORT="22"
SSH_KEY=""
HOST=""
PROVIDER=""
PROXY_PORT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --user) SSH_USER="$2"; shift 2 ;;
    --ssh-port) SSH_PORT="$2"; shift 2 ;;
    --key) SSH_KEY="$2"; shift 2 ;;
    --port) PROXY_PORT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

: "${HOST:?Usage: deploy.sh --provider <name> --host <VPS_IP> [--user root] [--ssh-port 22] [--key path]}"
: "${PROVIDER:?Usage: deploy.sh --provider <name> --host <VPS_IP> [--user root] [--ssh-port 22] [--key path]}"

PROVIDER_DIR="${SCRIPT_DIR}/providers/${PROVIDER}"
if [[ ! -f "${PROVIDER_DIR}/remote/install.sh" ]]; then
  echo "Unknown provider '${PROVIDER}' (expected ${PROVIDER_DIR}/remote/install.sh)" >&2
  echo "Available providers: $(ls "${SCRIPT_DIR}/providers" 2>/dev/null | tr '\n' ' ')" >&2
  exit 1
fi

SSH_OPTS=(-p "${SSH_PORT}")
[[ -n "${SSH_KEY}" ]] && SSH_OPTS+=(-i "${SSH_KEY}")

REMOTE_DIR="/opt/proxy-scripts/${PROVIDER}"

echo ">>> Uploading ${PROVIDER} scripts to ${SSH_USER}@${HOST}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${SSH_USER}@${HOST}" "mkdir -p ${REMOTE_DIR}"
scp "${SSH_OPTS[@]}" "${PROVIDER_DIR}"/remote/* "${SSH_USER}@${HOST}:${REMOTE_DIR}/"

echo ">>> Running remote install (provider: ${PROVIDER})"
PORT_ENV=""
[[ -n "${PROXY_PORT}" ]] && PORT_ENV="PROXY_PORT=${PROXY_PORT}"
ssh "${SSH_OPTS[@]}" "${SSH_USER}@${HOST}" \
  "chmod +x ${REMOTE_DIR}/*.sh && SERVER_IP=${HOST} ${PORT_ENV} ${REMOTE_DIR}/install.sh"

echo ">>> Fetching client-info.json"
mkdir -p "${SCRIPT_DIR}/output"
INFO_FILE="${SCRIPT_DIR}/output/${PROVIDER}-${HOST}-client-info.json"
scp "${SSH_OPTS[@]}" "${SSH_USER}@${HOST}:/opt/proxy/${PROVIDER}/client-info.json" "${INFO_FILE}"

echo ">>> Generating client profile"
"${SCRIPT_DIR}/generate-config.sh" "${INFO_FILE}"

echo ">>> Running external verification"
"${SCRIPT_DIR}/verify.sh" "${INFO_FILE}"
