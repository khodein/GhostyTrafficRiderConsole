#!/usr/bin/env bash
# Manages per-device clients of the xray-reality proxy and restarts the
# container so the change takes effect (active connections drop for 1-2 s;
# keys, port and everyone else's links stay the same).
#
# rename only changes the label (UUID and links keep working), so it does not
# restart the container.
#
# Usage: clients.sh list | add <name> | remove <name> | rename <old> <new>
set -euo pipefail

CONTAINER_NAME="xray-reality"
DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
  list)
    python3 "${DIR}/clients.py" list
    ;;
  add|remove)
    python3 "${DIR}/clients.py" "$1" "${2:?Usage: clients.sh $1 <name>}"
    docker restart "${CONTAINER_NAME}" >/dev/null
    echo "Container restarted"
    ;;
  rename)
    python3 "${DIR}/clients.py" rename "${2:?Usage: clients.sh rename <old> <new>}" "${3:?Usage: clients.sh rename <old> <new>}"
    ;;
  *)
    echo "Usage: clients.sh list | add <name> | remove <name> | rename <old> <new>" >&2
    exit 1
    ;;
esac
