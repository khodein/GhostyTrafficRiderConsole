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
    """Lists every provider available under proxy-scripts/providers/.

    A directory counts as a provider only if it has a
    remote/install.sh - that's the one file every provider contract
    requires (see README.md "Контракт провайдера").

    Returns:
        Provider names (directory names), sorted alphabetically. Empty
        list if the providers directory doesn't exist at all.
    """
    providers_dir = PROXY_SCRIPTS_DIR / "providers"
    if not providers_dir.exists():
        return []
    return sorted(
        p.name for p in providers_dir.iterdir() if (p / "remote" / "install.sh").exists()
    )


@dataclass
class ServerProfile:
    """One SSH connection profile - a "server" in the app's data model.

    Holds only connection details, not what's deployed on it (see
    proxy_dir() and friends below for that). Persisted as one entry in
    servers.yaml via save_servers()/load_servers().

    Args:
        name: Unique local identifier (also the on-disk folder name under
            ~/.config/ghosty-console/servers/).
        host: Hostname or IP address to SSH into.
        user: SSH username. Defaults to "root".
        port: SSH port. Defaults to 22.
        key_path: Path to a private key file. Empty string means "no key
            configured" - the app will prompt for a password before every
            SSH action instead, and never persist it.
    """

    name: str
    host: str
    user: str = "root"
    port: int = 22
    key_path: str = ""

    @property
    def uses_key(self) -> bool:
        """True if a key_path is configured, i.e. no password prompt is needed."""
        return bool(self.key_path)

    @property
    def state_dir(self) -> Path:
        """Root of this server's local state: ~/.config/ghosty-console/servers/<name>/."""
        return CONFIG_DIR / "servers" / self.name

    @property
    def proxies_dir(self) -> Path:
        """Directory holding one subfolder per locally-known proxy (provider)."""
        return self.state_dir / "proxies"

    def proxy_dir(self, provider: str) -> Path:
        """Root state directory for one specific proxy on this server.

        Args:
            provider: Provider name, e.g. "shadowsocks-xray".

        Returns:
            proxies_dir/<provider>.
        """
        return self.proxies_dir / provider

    def proxy_current_dir(self, provider: str) -> Path:
        """Where the latest known-good state for this proxy lives.

        Args:
            provider: Provider name, e.g. "shadowsocks-xray".

        Returns:
            proxy_dir(provider)/current - contains client-info.json and any
            other state files (certs, keys, ...) synced from the server.
        """
        return self.proxy_dir(provider) / "current"

    def proxy_history_dir(self, provider: str) -> Path:
        """Where past snapshots of this proxy's state live (used by Rollback).

        Args:
            provider: Provider name, e.g. "shadowsocks-xray".

        Returns:
            proxy_dir(provider)/history - one timestamped subfolder per
            past Deploy/Discover/Rollback sync.
        """
        return self.proxy_dir(provider) / "history"


def _ensure_dirs() -> None:
    """Creates CONFIG_DIR (~/.config/ghosty-console) if it doesn't exist yet."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_proxy_state(server_name: str, old_profile_name: str, provider: str) -> None:
    """Moves one legacy profile's on-disk state onto the new proxy layout.

    Old layout: servers/<old_profile_name>/{current,history}/ directly.
    New layout: servers/<server_name>/proxies/<provider>/{current,history}/.
    A no-op if the new location already exists (already migrated) or the
    old one doesn't (nothing to move).

    Args:
        server_name: Name the merged server profile will keep going forward.
        old_profile_name: Name the legacy flat profile used to have - equal
            to server_name for what used to be the "base" profile, or the
            old "<server>-<provider>" sibling name for extra proxies.
        provider: Provider this piece of state belongs to.
    """
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
    (nothing in servers.yaml has a "provider" field anymore).

    Args:
        raw: Parsed servers.yaml content (list of plain dicts, as loaded
            from YAML - not yet turned into ServerProfile instances).

    Returns:
        A new list of dicts in the current (post-migration) shape. Equal
        to `raw` unchanged if there was nothing legacy to migrate.
    """
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
    """Reads every known server profile from servers.yaml.

    Runs the legacy-profile migration first (see
    _migrate_legacy_servers()); if that changes anything, the migrated
    shape is written back to servers.yaml immediately, so the migration
    only ever needs to run once per profile.

    Returns:
        All server profiles currently known locally. Empty list if
        servers.yaml doesn't exist yet.
    """
    _ensure_dirs()
    if not SERVERS_FILE.exists():
        return []
    raw = yaml.safe_load(SERVERS_FILE.read_text()) or []
    migrated = _migrate_legacy_servers(raw)
    if migrated != raw:
        SERVERS_FILE.write_text(yaml.safe_dump(migrated, sort_keys=False))
    return [ServerProfile(**item) for item in migrated]


def save_servers(servers: list[ServerProfile]) -> None:
    """Overwrites servers.yaml with exactly the given list of profiles.

    Args:
        servers: The full list of server profiles to persist - not a
            partial update; anything not included here is dropped from
            servers.yaml (though its on-disk state directory is untouched).
    """
    _ensure_dirs()
    SERVERS_FILE.write_text(yaml.safe_dump([asdict(s) for s in servers], sort_keys=False))


def add_server(profile: ServerProfile) -> None:
    """Adds a new server profile, or replaces an existing one with the same name.

    Also creates the server's state_dir on disk so its proxies/ folder is
    ready to receive Deploy/Discover results.

    Args:
        profile: The server profile to save.
    """
    servers = [s for s in load_servers() if s.name != profile.name]
    servers.append(profile)
    save_servers(servers)
    profile.state_dir.mkdir(parents=True, exist_ok=True)


def remove_server(name: str) -> None:
    """Deletes a server profile and all of its local state (including every proxy).

    Only affects local bookkeeping - nothing is changed on the actual VPS.

    Args:
        name: Name of the server profile to remove.
    """
    servers = [s for s in load_servers() if s.name != name]
    save_servers(servers)
    state_dir = CONFIG_DIR / "servers" / name
    if state_dir.exists():
        shutil.rmtree(state_dir)


def list_proxies(profile: ServerProfile) -> list[str]:
    """Lists providers with locally known state for this server.

    "Locally known" means deployed to, or pulled down via Discover, from
    this device - not necessarily everything actually running on the VPS
    (run Discover to reconcile that).

    Args:
        profile: The server to inspect.

    Returns:
        Provider names, sorted alphabetically. Empty list if nothing is
        known yet.
    """
    if not profile.proxies_dir.exists():
        return []
    return sorted(p.name for p in profile.proxies_dir.iterdir() if p.is_dir())


def remove_proxy(profile: ServerProfile, provider: str) -> None:
    """Drops local knowledge of this proxy (history included).

    Does not touch the server - see deploy.remove_config() for actually
    tearing down the remote container/config.

    Args:
        profile: The server the proxy belongs to.
        provider: Provider name of the proxy to forget locally.
    """
    proxy_dir = profile.proxy_dir(provider)
    if proxy_dir.exists():
        shutil.rmtree(proxy_dir)


def new_proxy_snapshot_dir(profile: ServerProfile, provider: str) -> Path:
    """Creates a fresh, empty, timestamped snapshot folder for one proxy.

    Used by deploy.py right before pulling state down from the server, so
    each Deploy/Discover/Rollback leaves behind a distinct history entry.

    Args:
        profile: The server the proxy belongs to.
        provider: Provider name of the proxy being snapshotted.

    Returns:
        Path to the new, already-created snapshot directory (named after
        the current UTC timestamp).
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = profile.proxy_history_dir(provider) / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_proxy_snapshots(profile: ServerProfile, provider: str) -> list[str]:
    """Lists past snapshots available for Rollback, newest first.

    Args:
        profile: The server the proxy belongs to.
        provider: Provider name of the proxy to list snapshots for.

    Returns:
        Snapshot folder names (UTC timestamps), sorted newest-first. Empty
        list if this proxy has no history yet.
    """
    history_dir = profile.proxy_history_dir(provider)
    if not history_dir.exists():
        return []
    return sorted((p.name for p in history_dir.iterdir() if p.is_dir()), reverse=True)
