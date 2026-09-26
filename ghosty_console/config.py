"""Local server registry and per-server/per-proxy state paths.

Model: a "server" is just an SSH connection profile (host/user/port/key).
A server can have zero or more "proxies" deployed on it - one per
provider - discovered via Discover or created via Deploy. Passwords are
never written to disk: a server either points at an SSH key file, or
leaves key_path empty, in which case the app prompts for a password at
the start of every action and keeps it only in memory.
"""
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".config" / "ghosty-console"
SERVERS_FILE = CONFIG_DIR / "servers.yaml"
PROXY_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "proxy-scripts"


def list_providers() -> list[str]:
    providers_dir = PROXY_SCRIPTS_DIR / "providers"
    if not providers_dir.exists():
        return []
    return sorted(
        p.name for p in providers_dir.iterdir() if (p / "remote" / "install.sh").exists()
    )


@dataclass
class ServerProfile:
    name: str
    host: str
    user: str = "root"
    port: int = 22
    key_path: str = ""

    @property
    def uses_key(self) -> bool:
        return bool(self.key_path)

    @property
    def state_dir(self) -> Path:
        return CONFIG_DIR / "servers" / self.name

    @property
    def proxies_dir(self) -> Path:
        return self.state_dir / "proxies"

    def proxy_dir(self, provider: str) -> Path:
        return self.proxies_dir / provider

    def proxy_current_dir(self, provider: str) -> Path:
        return self.proxy_dir(provider) / "current"

    def proxy_history_dir(self, provider: str) -> Path:
        return self.proxy_dir(provider) / "history"


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_proxy_state(server_name: str, old_profile_name: str, provider: str) -> None:
    old_dir = CONFIG_DIR / "servers" / old_profile_name
    new_dir = CONFIG_DIR / "servers" / server_name / "proxies" / provider
    if new_dir.exists() or not old_dir.exists():
        return
    new_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("current", "history"):
        old_sub = old_dir / sub
        if old_sub.exists():
            shutil.move(str(old_sub), str(new_dir / sub))
    if old_profile_name != server_name:
        shutil.rmtree(old_dir, ignore_errors=True)


def _migrate_legacy_servers(raw: list[dict]) -> list[dict]:
    """One-time, automatic upgrade from the old data shape, where a
    "server" and one of its proxies were the same flat profile
    (`provider`/`proxy_port` fields directly on it; extra proxies on the
    same host were stored as separate sibling profiles named
    "<server>-<provider>"). Folds every legacy profile sharing a host into
    one server entry and moves each one's on-disk state under
    servers/<server>/proxies/<provider>/. No-op once already migrated
    (nothing in servers.yaml has a "provider" field anymore)."""
    legacy = [p for p in raw if "provider" in p]
    if not legacy:
        return raw

    by_host: dict[str, list[dict]] = {}
    for p in legacy:
        by_host.setdefault(p["host"], []).append(p)

    migrated: list[dict] = [p for p in raw if "provider" not in p]
    for host, entries in by_host.items():
        entries.sort(key=lambda e: len(e["name"]))  # shortest name = the original base profile
        base = entries[0]
        server_name = base["name"]
        migrated.append(
            {
                "name": server_name,
                "host": base["host"],
                "user": base.get("user", "root"),
                "port": base.get("port", 22),
                "key_path": base.get("key_path", ""),
            }
        )
        for entry in entries:
            _migrate_proxy_state(server_name, entry["name"], entry["provider"])

    return migrated


def load_servers() -> list[ServerProfile]:
    _ensure_dirs()
    if not SERVERS_FILE.exists():
        return []
    raw = yaml.safe_load(SERVERS_FILE.read_text()) or []
    migrated = _migrate_legacy_servers(raw)
    if migrated != raw:
        SERVERS_FILE.write_text(yaml.safe_dump(migrated, sort_keys=False))
    return [ServerProfile(**item) for item in migrated]


def save_servers(servers: list[ServerProfile]) -> None:
    _ensure_dirs()
    SERVERS_FILE.write_text(yaml.safe_dump([asdict(s) for s in servers], sort_keys=False))


def add_server(profile: ServerProfile) -> None:
    servers = [s for s in load_servers() if s.name != profile.name]
    servers.append(profile)
    save_servers(servers)
    profile.state_dir.mkdir(parents=True, exist_ok=True)


def remove_server(name: str) -> None:
    servers = [s for s in load_servers() if s.name != name]
    save_servers(servers)
    state_dir = CONFIG_DIR / "servers" / name
    if state_dir.exists():
        shutil.rmtree(state_dir)


def list_proxies(profile: ServerProfile) -> list[str]:
    """Providers with locally known state for this server (deployed to, or
    pulled down via Discover, from this device)."""
    if not profile.proxies_dir.exists():
        return []
    return sorted(p.name for p in profile.proxies_dir.iterdir() if p.is_dir())


def remove_proxy(profile: ServerProfile, provider: str) -> None:
    """Drops local knowledge of this proxy (history included). Does not
    touch the server - see deploy.remove_config for that."""
    proxy_dir = profile.proxy_dir(provider)
    if proxy_dir.exists():
        shutil.rmtree(proxy_dir)


def new_proxy_snapshot_dir(profile: ServerProfile, provider: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = profile.proxy_history_dir(provider) / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_proxy_snapshots(profile: ServerProfile, provider: str) -> list[str]:
    history_dir = profile.proxy_history_dir(provider)
    if not history_dir.exists():
        return []
    return sorted((p.name for p in history_dir.iterdir() if p.is_dir()), reverse=True)
