"""Provider-agnostic deploy logic: tests/test_deploy.py
Covers: ghosty_console/deploy.py (deploy, discover, regenerate_config) with
a faked SSH session - never touches a real server. A server can have
several proxies (one per provider); every function below except discover()
takes the provider explicitly.

Template for a new deploy.py-level test:
    def test_my_thing(isolated_config, monkeypatch):
        from ghosty_console import deploy as deploy_mod
        from ghosty_console.config import ServerProfile, add_server
        from tests.fakes import make_fake_ssh_session

        profile = ServerProfile(name="x", host="203.0.113.1")
        add_server(profile)
        monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session({...}))
        ... call deploy_mod.<function>(profile, "shadowsocks-xray", None, lines.append) ...
"""
import json

from ghosty_console import deploy as deploy_mod
from ghosty_console.config import ServerProfile, add_server, list_proxies
from tests.fakes import make_fake_ssh_session
from tests.sample_client_info import SHADOWSOCKS_XRAY_INFO, XRAY_REALITY_INFO


def _remote_info_path(provider: str) -> str:
    """Builds the remote client-info.json path a fake SSH session should serve for this provider."""
    return f"/opt/proxy/{provider}/client-info.json"


def test_deploy_syncs_client_info_locally(isolated_config, monkeypatch):
    """deploy() runs install.sh over (fake) SSH, then pulls the resulting
    client-info.json down into the proxy's local current/ directory and
    registers the proxy in list_proxies()."""
    profile = ServerProfile(name="node-a", host="203.0.113.7")
    add_server(profile)

    remote_files = {_remote_info_path("shadowsocks-xray"): SHADOWSOCKS_XRAY_INFO}
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files))

    info = deploy_mod.deploy(profile, "shadowsocks-xray", "", None, lambda line: None)

    assert info == SHADOWSOCKS_XRAY_INFO
    stored = json.loads((profile.proxy_current_dir("shadowsocks-xray") / "client-info.json").read_text())
    assert stored == SHADOWSOCKS_XRAY_INFO
    assert list_proxies(profile) == ["shadowsocks-xray"]


def test_deploy_passes_proxy_port_to_install_command(isolated_config, monkeypatch):
    """When a proxy_port is given, deploy() prefixes the remote install.sh
    invocation with PROXY_PORT=<port>, so a first install picks it up."""
    profile = ServerProfile(name="node-b", host="203.0.113.7")
    add_server(profile)

    commands: list[str] = []

    def on_command(command, on_line):
        commands.append(command)
        return None  # let the default handling still run too

    remote_files = {_remote_info_path("shadowsocks-xray"): SHADOWSOCKS_XRAY_INFO}
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files, on_command))

    deploy_mod.deploy(profile, "shadowsocks-xray", "8443", None, lambda line: None)

    assert any("PROXY_PORT=8443" in c and "install.sh" in c for c in commands)


def test_deploy_redeploy_omits_proxy_port(isolated_config, monkeypatch):
    """Re-deploying an existing proxy (empty proxy_port) must not force a
    PROXY_PORT env var - install.sh already keeps whatever port it picked
    on first install."""
    profile = ServerProfile(name="node-c", host="203.0.113.7")
    add_server(profile)

    commands: list[str] = []

    def on_command(command, on_line):
        commands.append(command)
        return None

    remote_files = {_remote_info_path("shadowsocks-xray"): SHADOWSOCKS_XRAY_INFO}
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files, on_command))

    deploy_mod.deploy(profile, "shadowsocks-xray", "", None, lambda line: None)

    install_commands = [c for c in commands if "install.sh" in c]
    assert install_commands and all("PROXY_PORT" not in c for c in install_commands)


def test_discover_finds_multiple_providers_on_one_server(isolated_config, monkeypatch):
    """discover() finds every /opt/proxy/<provider>/client-info.json on the
    (fake) server, syncs each one into this server's local proxies/, and
    returns one result dict per provider found."""
    profile = ServerProfile(name="myvps", host="203.0.113.7")
    add_server(profile)

    remote_files = {
        _remote_info_path("shadowsocks-xray"): SHADOWSOCKS_XRAY_INFO,
        _remote_info_path("xray-reality"): XRAY_REALITY_INFO,
    }
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files))

    found = deploy_mod.discover(profile, None, lambda line: None)

    assert {item["provider"] for item in found} == {"shadowsocks-xray", "xray-reality"}
    assert set(list_proxies(profile)) == {"shadowsocks-xray", "xray-reality"}

    for provider, expected in [
        ("shadowsocks-xray", SHADOWSOCKS_XRAY_INFO),
        ("xray-reality", XRAY_REALITY_INFO),
    ]:
        stored = json.loads((profile.proxy_current_dir(provider) / "client-info.json").read_text())
        assert stored == expected


def test_discover_reports_when_nothing_found(isolated_config, monkeypatch):
    """discover() returns an empty list and logs a "nothing deployed" line
    when the (fake) server has no /opt/proxy/*/client-info.json at all -
    and leaves the server's local proxies list empty too."""
    profile = ServerProfile(name="empty-vps", host="203.0.113.9")
    add_server(profile)

    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session({}))

    lines: list[str] = []
    found = deploy_mod.discover(profile, None, lines.append)

    assert found == []
    assert any("nothing deployed" in line for line in lines)
    assert list_proxies(profile) == []


def test_regenerate_config_uses_local_cache_without_ssh(isolated_config, monkeypatch):
    """When a local client-info.json already exists, regenerate_config()
    rebuilds the client profile from it directly and never even
    constructs an SSHSession (asserted via a session class that raises
    if instantiated)."""
    profile = ServerProfile(name="cached", host="203.0.113.55")
    add_server(profile)
    current = profile.proxy_current_dir("shadowsocks-xray")
    current.mkdir(parents=True)
    (current / "client-info.json").write_text(json.dumps(SHADOWSOCKS_XRAY_INFO))

    class ExplodingSSHSession:
        def __init__(self, *a, **k):
            raise AssertionError("SSHSession must not be constructed when a local cache exists")

    monkeypatch.setattr(deploy_mod, "SSHSession", ExplodingSSHSession)

    lines: list[str] = []
    path = deploy_mod.regenerate_config(profile, "shadowsocks-xray", None, lines.append)

    assert path == str(current / "client-info.json")
    assert any("no SSH needed" in line for line in lines)


def test_regenerate_config_falls_back_to_ssh_when_cache_missing(isolated_config, monkeypatch):
    """When there's no local client-info.json (e.g. it was deleted),
    regenerate_config() connects over (fake) SSH to fetch it fresh from
    the server before rebuilding the client profile."""
    profile = ServerProfile(name="lost-config", host="203.0.113.55")
    add_server(profile)
    assert not (profile.proxy_current_dir("shadowsocks-xray") / "client-info.json").exists()

    remote_files = {_remote_info_path("shadowsocks-xray"): SHADOWSOCKS_XRAY_INFO}
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files))

    lines: list[str] = []
    deploy_mod.regenerate_config(profile, "shadowsocks-xray", "irrelevant", lines.append)

    assert any("fetching it from the server" in line for line in lines)
    stored = json.loads((profile.proxy_current_dir("shadowsocks-xray") / "client-info.json").read_text())
    assert stored == SHADOWSOCKS_XRAY_INFO
