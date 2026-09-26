"""Local server registry: tests/test_config.py
Covers: ghosty_console/config.py (add/load/remove servers, proxies list,
legacy-profile migration).

Template for a new config.py-level test:
    def test_my_thing(isolated_config):
        from ghosty_console.config import ServerProfile, add_server
        add_server(ServerProfile(name="x", host="203.0.113.1"))
        ...
"""
import json

import yaml

from ghosty_console.config import (
    ServerProfile,
    add_server,
    list_proxies,
    load_servers,
    new_proxy_snapshot_dir,
    remove_proxy,
    remove_server,
)


def test_add_load_remove_roundtrip(isolated_config):
    """add_server() persists a profile and creates its state_dir;
    load_servers() reads it back; remove_server() deletes both the
    registry entry and the state_dir from disk."""
    profile = ServerProfile(name="node-a", host="203.0.113.10")
    add_server(profile)

    assert [s.name for s in load_servers()] == ["node-a"]
    assert profile.state_dir.exists()

    remove_server("node-a")

    assert load_servers() == []
    assert not profile.state_dir.exists()


def test_add_server_replaces_same_name(isolated_config):
    """Calling add_server() twice with the same profile name overwrites
    the first entry instead of creating a duplicate."""
    add_server(ServerProfile(name="node-a", host="203.0.113.10"))
    add_server(ServerProfile(name="node-a", host="203.0.113.99"))

    servers = load_servers()
    assert len(servers) == 1
    assert servers[0].host == "203.0.113.99"


def test_list_proxies_and_remove_proxy(isolated_config):
    """list_proxies() reflects whatever proxy subfolders exist under a
    server's proxies/ dir; remove_proxy() deletes just that proxy's state
    without touching the rest of the server's local data."""
    profile = ServerProfile(name="myvps", host="203.0.113.7")
    add_server(profile)
    assert list_proxies(profile) == []

    snapshot = new_proxy_snapshot_dir(profile, "shadowsocks-xray")
    (snapshot / "client-info.json").write_text(json.dumps({"provider": "shadowsocks-xray"}))

    assert list_proxies(profile) == ["shadowsocks-xray"]

    remove_proxy(profile, "shadowsocks-xray")
    assert list_proxies(profile) == []
    assert profile.state_dir.exists()  # only the proxy is gone, not the server


def test_migrates_legacy_single_provider_profile(isolated_config):
    """Older versions stored `provider`/`proxy_port` directly on the server
    profile, with its client-info.json under servers/<name>/current/
    (not servers/<name>/proxies/<provider>/current/)."""
    config_dir = isolated_config.CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "servers.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "name": "old-node",
                    "host": "203.0.113.20",
                    "user": "root",
                    "port": 22,
                    "key_path": "",
                    "provider": "shadowsocks-xray",
                    "proxy_port": "",
                }
            ]
        )
    )
    legacy_current = config_dir / "servers" / "old-node" / "current"
    legacy_current.mkdir(parents=True)
    (legacy_current / "client-info.json").write_text(json.dumps({"provider": "shadowsocks-xray"}))

    servers = load_servers()

    assert len(servers) == 1
    migrated = servers[0]
    assert migrated.name == "old-node"
    assert migrated.host == "203.0.113.20"
    assert list_proxies(migrated) == ["shadowsocks-xray"]
    assert (migrated.proxy_current_dir("shadowsocks-xray") / "client-info.json").exists()
    assert not legacy_current.exists()

    # migration persisted to disk - reloading doesn't re-trigger it or duplicate anything
    servers_again = load_servers()
    assert len(servers_again) == 1


def test_migrates_and_merges_sibling_profiles_by_host(isolated_config):
    """Discover used to create a separate sibling profile
    ("<name>-<provider>") for each extra provider found on the same host -
    those should collapse into one server with two proxies."""
    config_dir = isolated_config.CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "servers.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "name": "myvps",
                    "host": "203.0.113.30",
                    "user": "root",
                    "port": 22,
                    "key_path": "",
                    "provider": "shadowsocks-xray",
                    "proxy_port": "",
                },
                {
                    "name": "myvps-xray-reality",
                    "host": "203.0.113.30",
                    "user": "root",
                    "port": 22,
                    "key_path": "",
                    "provider": "xray-reality",
                    "proxy_port": "",
                },
            ]
        )
    )
    for legacy_name, provider in [("myvps", "shadowsocks-xray"), ("myvps-xray-reality", "xray-reality")]:
        legacy_current = config_dir / "servers" / legacy_name / "current"
        legacy_current.mkdir(parents=True)
        (legacy_current / "client-info.json").write_text(json.dumps({"provider": provider}))

    servers = load_servers()

    assert [s.name for s in servers] == ["myvps"]
    merged = servers[0]
    assert merged.host == "203.0.113.30"
    assert set(list_proxies(merged)) == {"shadowsocks-xray", "xray-reality"}
    assert not (config_dir / "servers" / "myvps-xray-reality").exists()
