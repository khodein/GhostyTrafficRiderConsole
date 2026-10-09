"""Per-device clients on the server side: tests/test_xray_clients.py
Covers: proxy-scripts/providers/xray-reality/remote/clients.py (run against
a temp state dir, the way clients.sh runs it on the VPS) and the share links
that xray-reality/generate-config.sh builds for every device.
"""
import json
import os
import subprocess
import sys

from ghosty_console.config import PROXY_SCRIPTS_DIR

REALITY_DIR = PROXY_SCRIPTS_DIR / "providers" / "xray-reality"
CLIENTS_PY = REALITY_DIR / "remote" / "clients.py"
GENERATE = REALITY_DIR / "generate-config.sh"
FIRST_UUID = "11111111-2222-3333-4444-555555555555"


def _state_dir(tmp_path):
    """Creates a state dir like install.sh leaves it before clients.py ever ran."""
    (tmp_path / "proxy.env").write_text("XRAY_PORT=443\nXRAY_SITE=www.apple.com\n")
    (tmp_path / "proxy.env.keys").write_text(
        f"XRAY_CLIENT_ID={FIRST_UUID}\nXRAY_SHORT_ID=0123456789abcdef\n"
        "XRAY_PRIVATE_KEY=PRIV\nXRAY_PUBLIC_KEY=PUB\n"
    )
    return tmp_path


def _run(state, *args):
    """Runs clients.py against the given state dir."""
    env = {**os.environ, "PROXY_STATE_DIR": str(state), "SERVER_IP": "203.0.113.7"}
    return subprocess.run([sys.executable, str(CLIENTS_PY), *args], capture_output=True, text=True, env=env)


def _server_ids(state):
    """UUIDs Xray will accept, as written to server.json."""
    server = json.loads((state / "server.json").read_text())
    return [c["id"] for c in server["inbounds"][0]["settings"]["clients"]]


def test_render_turns_existing_client_into_default_device(tmp_path):
    """First run keeps the pre-existing UUID as device "default", so links issued earlier keep working."""
    state = _state_dir(tmp_path)
    assert _run(state, "render").returncode == 0
    info = json.loads((state / "client-info.json").read_text())
    assert info["uuid"] == FIRST_UUID
    assert info["clients"] == [{"name": "default", "uuid": FIRST_UUID}]
    assert _server_ids(state) == [FIRST_UUID]


def test_server_accepts_clients_of_any_core_version(tmp_path):
    """Xray 26.x rejects clients older than v26.3.27 unless minClientVer is lowered -
    sing-box based apps (Hiddify) would otherwise fail authentication."""
    state = _state_dir(tmp_path)
    _run(state, "render")
    server = json.loads((state / "server.json").read_text())
    assert server["inbounds"][0]["streamSettings"]["realitySettings"]["minClientVer"] == "0.0.0"


def test_add_and_remove_device_updates_server_and_client_info(tmp_path):
    """add gives the device its own UUID in server.json and client-info.json; remove revokes only that one."""
    state = _state_dir(tmp_path)
    _run(state, "render")

    assert _run(state, "add", "iphone").returncode == 0
    info = json.loads((state / "client-info.json").read_text())
    iphone = next(c["uuid"] for c in info["clients"] if c["name"] == "iphone")
    assert iphone != FIRST_UUID
    assert _server_ids(state) == [FIRST_UUID, iphone]

    assert _run(state, "remove", "iphone").returncode == 0
    assert _server_ids(state) == [FIRST_UUID]


def test_invalid_duplicate_unknown_and_last_device_are_rejected(tmp_path):
    """Bad names, duplicates, unknown names and removing the last device all fail without changing state."""
    state = _state_dir(tmp_path)
    _run(state, "render")
    _run(state, "add", "iphone")

    assert _run(state, "add", "bad;name").returncode != 0
    assert _run(state, "add", "iphone").returncode != 0
    assert _run(state, "remove", "nope").returncode != 0
    assert _run(state, "remove", "iphone").returncode == 0
    assert _run(state, "remove", "default").returncode != 0
    assert _server_ids(state) == [FIRST_UUID]


def _generate(tmp_path, label=None):
    """Runs generate-config.sh on a two-device client-info.json; returns the saved link lines."""
    info = {
        "provider": "xray-reality", "ip": "203.0.113.7", "port": 443, "uuid": "u-1",
        "public_key": "PBK", "short_id": "abcd", "site_name": "www.apple.com",
        "flow": "xtls-rprx-vision", "fingerprint": "chrome",
        "clients": [{"name": "default", "uuid": "u-1"}, {"name": "My iPhone", "uuid": "u-2"}],
    }
    info_file = tmp_path / "client-info.json"
    info_file.write_text(json.dumps(info))
    env = {**os.environ}
    env.pop("SERVER_LABEL", None)
    if label is not None:
        env["SERVER_LABEL"] = label
    result = subprocess.run(
        [str(GENERATE), str(info_file), str(tmp_path / "out.yaml")], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    return (tmp_path / "out.txt").read_text().splitlines()


def test_generate_config_builds_a_link_per_device(tmp_path):
    """One vless:// link per device, each with its own UUID; without a server
    label the profile title is just the (URL-encoded) device name."""
    links = _generate(tmp_path)
    assert len(links) == 2
    assert links[0].startswith("vless://u-1@203.0.113.7:443?") and links[0].endswith("#default")
    assert links[1].startswith("vless://u-2@203.0.113.7:443?") and links[1].endswith("#My%20iPhone")


def test_generate_config_title_is_server_label_and_device(tmp_path):
    """With SERVER_LABEL the title is "<server> · <device>", URL-encoded."""
    links = _generate(tmp_path, label="gmail")
    assert links[0].endswith("#gmail%20%C2%B7%20default")
    assert links[1].endswith("#gmail%20%C2%B7%20My%20iPhone")


def test_free_device_names_are_accepted_and_shell_unsafe_ones_rejected(tmp_path):
    """Spaces and non-Latin letters are fine; characters that matter to a shell are not."""
    state = _state_dir(tmp_path)
    _run(state, "render")
    assert _run(state, "add", "Мой iPhone").returncode == 0
    for bad in ("a;b", "a$b", "a'b", 'a"b', "a`b", "a/b", " lead", "trail ", ""):
        assert _run(state, "add", bad).returncode != 0, bad


def test_rename_keeps_the_key(tmp_path):
    """rename changes only the label: the UUID (and so the imported link) keeps working."""
    state = _state_dir(tmp_path)
    _run(state, "render")
    assert _run(state, "rename", "default", "Mac Pro").returncode == 0
    info = json.loads((state / "client-info.json").read_text())
    assert info["clients"] == [{"name": "Mac Pro", "uuid": FIRST_UUID}]
    assert _server_ids(state) == [FIRST_UUID]


def test_rename_rejects_unknown_duplicate_and_invalid_names(tmp_path):
    """Renaming a missing device, onto a taken name, or to an invalid name fails and changes nothing."""
    state = _state_dir(tmp_path)
    _run(state, "render")
    _run(state, "add", "iphone")
    assert _run(state, "rename", "nope", "x").returncode != 0
    assert _run(state, "rename", "default", "iphone").returncode != 0
    assert _run(state, "rename", "default", "bad;name").returncode != 0
    names = [c["name"] for c in json.loads((state / "client-info.json").read_text())["clients"]]
    assert names == ["default", "iphone"]
