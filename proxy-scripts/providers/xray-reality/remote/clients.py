#!/usr/bin/env python3
"""Per-device clients (VLESS UUIDs) for the xray-reality proxy.

Runs on the VPS. State lives in $PROXY_STATE_DIR (default
/opt/proxy/xray-reality):
  proxy.env, proxy.env.keys  - written by install.sh (port, site, keys)
  clients.json               - [{"name": ..., "uuid": ...}, ...]
  server.json                - Xray inbound config, rendered from the above
  client-info.json           - what the local console downloads to build links

Usage: clients.py render | list | add <name> | remove <name> | rename <old> <new>
render is called by install.sh; add/remove/rename are called through clients.sh
(add/remove also restart the container; rename only changes a label). SERVER_IP is only needed by render when
client-info.json doesn't exist yet.
"""
import json
import os
import re
import sys
import uuid
from pathlib import Path

PROVIDER = "xray-reality"
STATE_DIR = Path(os.environ.get("PROXY_STATE_DIR", f"/opt/proxy/{PROVIDER}"))
# Letters (any language), digits, space, "_", "-", "."; no leading/trailing space.
NAME_RE = re.compile(r"^(?!\s)[\w .-]{1,32}(?<!\s)$")


def read_env(path):
    """Parses a KEY=VALUE file (as written by install.sh) into a dict."""
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def write_file(path, text):
    """Writes text in place (same inode) with 0600 permissions.

    server.json is bind-mounted into the container as a single file, so it
    must be rewritten in place - replacing it via rename would leave the
    container looking at the old, deleted file.
    """
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def load_clients():
    """Returns the client list, creating clients.json on first use from the
    single client install.sh generated before per-device keys existed (it
    becomes "default", so already-issued links keep working)."""
    clients_file = STATE_DIR / "clients.json"
    if clients_file.exists():
        return json.loads(clients_file.read_text())
    keys = read_env(STATE_DIR / "proxy.env.keys")
    clients = [{"name": "default", "uuid": keys["XRAY_CLIENT_ID"]}]
    save_clients(clients)
    return clients


def save_clients(clients):
    """Persists the client list to clients.json."""
    write_file(STATE_DIR / "clients.json", json.dumps(clients, indent=2) + "\n")


def render():
    """Rewrites server.json and client-info.json from the current state."""
    env = read_env(STATE_DIR / "proxy.env")
    keys = read_env(STATE_DIR / "proxy.env.keys")
    clients = load_clients()
    port = int(env["XRAY_PORT"])
    site = env["XRAY_SITE"]

    info_file = STATE_DIR / "client-info.json"
    ip = os.environ.get("SERVER_IP")
    if not ip and info_file.exists():
        ip = json.loads(info_file.read_text())["ip"]
    if not ip:
        sys.exit("SERVER_IP is not set and there is no client-info.json to take it from")

    server = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": c["uuid"], "flow": "xtls-rprx-vision"} for c in clients],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{site}:443",
                        "xver": 0,
                        "serverNames": [site],
                        # Xray 26.x refuses clients that advertise a core older than
                        # v26.3.27 by default; sing-box based clients (Hiddify, ...)
                        # advertise an older version and were rejected as "invalid".
                        "minClientVer": "0.0.0",
                        "privateKey": keys["XRAY_PRIVATE_KEY"],
                        "shortIds": [keys["XRAY_SHORT_ID"]],
                    },
                },
            }
        ],
        "outbounds": [{"protocol": "freedom"}],
    }
    write_file(STATE_DIR / "server.json", json.dumps(server, indent=2) + "\n")

    info = {
        "provider": PROVIDER,
        "ip": ip,
        "port": port,
        "uuid": clients[0]["uuid"],
        "public_key": keys["XRAY_PUBLIC_KEY"],
        "short_id": keys["XRAY_SHORT_ID"],
        "site_name": site,
        "flow": "xtls-rprx-vision",
        "fingerprint": "chrome",
        "clients": clients,
    }
    write_file(info_file, json.dumps(info, indent=2) + "\n")


def check_name(name):
    """Exits with an error unless name is a safe device name."""
    if not NAME_RE.match(name):
        sys.exit("device name must be 1-32 chars: letters, digits, space, _ - .")


def main(argv):
    """CLI entry point; see the module docstring for the commands."""
    command = argv[1] if len(argv) > 1 else ""
    if command == "render":
        render()
    elif command == "list":
        for c in load_clients():
            print(f"{c['name']}\t{c['uuid']}")
    elif command == "add" and len(argv) == 3:
        check_name(argv[2])
        clients = load_clients()
        if any(c["name"] == argv[2] for c in clients):
            sys.exit(f"device '{argv[2]}' already exists")
        clients.append({"name": argv[2], "uuid": str(uuid.uuid4())})
        save_clients(clients)
        render()
        print(f"added device '{argv[2]}'")
    elif command == "remove" and len(argv) == 3:
        clients = load_clients()
        left = [c for c in clients if c["name"] != argv[2]]
        if len(left) == len(clients):
            sys.exit(f"device '{argv[2]}' not found")
        if not left:
            sys.exit("cannot remove the last device - the proxy would have no clients")
        save_clients(left)
        render()
        print(f"removed device '{argv[2]}'")
    elif command == "rename" and len(argv) == 4:
        check_name(argv[3])
        clients = load_clients()
        target = next((c for c in clients if c["name"] == argv[2]), None)
        if target is None:
            sys.exit(f"device '{argv[2]}' not found")
        if any(c["name"] == argv[3] for c in clients):
            sys.exit(f"device '{argv[3]}' already exists")
        target["name"] = argv[3]
        save_clients(clients)
        render()
        print(f"renamed device '{argv[2]}' to '{argv[3]}'")
    else:
        sys.exit("usage: clients.py render | list | add <name> | remove <name> | rename <old> <new>")


if __name__ == "__main__":
    main(sys.argv)
