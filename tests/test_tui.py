"""TUI screen flows: tests/test_tui.py
Covers: ghosty_console/app.py + screens/* end-to-end, headless (Textual's
run_test), without a real terminal or a real server. Navigation is
three levels: server list -> server dashboard (its proxies table) ->
proxy detail (Deploy/Verify/Rollback/... for one provider on that server).

Template for a new TUI test:
    def test_my_flow(isolated_config):
        async def scenario():
            app = GhostyApp()
            async with app.run_test(size=(100, 50)) as pilot:
                await pilot.pause()
                ... await pilot.press(...) / await pilot.click("#some-id") ...
        asyncio.run(scenario())

Notes:
- size=(100, 50) avoids Pilot.click() raising OutOfBounds on the default
  80x24 terminal size once the action bar has more than a few buttons.
- Screens pushed with push_screen stay in memory; go back with `escape`/`b`,
  don't expect on_mount to fire again (use on_screen_resume for that).
- No pytest-asyncio dependency: each test wraps its scenario in
  asyncio.run() the same way the app itself is a sync entrypoint.
"""
import asyncio

from ghosty_console import deploy as deploy_mod
from ghosty_console.app import GhostyApp
from ghosty_console.config import ServerProfile, add_server
from ghosty_console.screens.add_server import AddServerScreen
from ghosty_console.screens.password_prompt import PasswordPromptScreen
from ghosty_console.screens.proxy_detail import ProxyDetailScreen
from ghosty_console.screens.server_dashboard import ServerDashboardScreen
from tests.fakes import make_fake_ssh_session
from tests.sample_client_info import SHADOWSOCKS_XRAY_INFO, XRAY_REALITY_INFO
from textual.widgets import DataTable, Input


def test_add_server_flow_jumps_to_dashboard_and_auto_discovers(isolated_config):
    """Adding a server (no ssh key configured) should land straight on its
    dashboard and auto-trigger Discover - which, with no key, means a
    password prompt pops up immediately, without a manual Discover click."""

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()

            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, AddServerScreen)

            app.screen.query_one("#name", Input).value = "test-node"
            app.screen.query_one("#host", Input).value = "203.0.113.42"
            await pilot.click("#save")
            await pilot.pause(0.3)

            assert isinstance(app.screen, PasswordPromptScreen)

            await pilot.click("#cancel")
            await pilot.pause(0.3)
            assert isinstance(app.screen, ServerDashboardScreen)
            assert app.screen.profile.name == "test-node"

            await pilot.press("escape")
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.row_count == 1

    asyncio.run(scenario())


def test_adding_a_server_with_a_key_shows_all_its_proxies_in_the_dashboard(
    isolated_config, monkeypatch
):
    """The real-world scenario: connect to a server by host+login (here via
    an ssh key, so no password prompt gets in the way) and, without any
    extra manual step, immediately see every proxy already deployed on it
    listed in ONE server's dashboard - not as separate top-level servers."""
    remote_files = {
        "/opt/proxy/shadowsocks-xray/client-info.json": SHADOWSOCKS_XRAY_INFO,
        "/opt/proxy/xray-reality/client-info.json": XRAY_REALITY_INFO,
    }
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files))

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()

            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, AddServerScreen)

            app.screen.query_one("#name", Input).value = "myvps"
            app.screen.query_one("#host", Input).value = "203.0.113.7"
            app.screen.query_one("#key_path", Input).value = "/fake/key"
            await pilot.click("#save")
            await pilot.pause(0.5)

            # No password prompt (key configured) - straight to the
            # dashboard, with Discover already having run against it.
            assert isinstance(app.screen, ServerDashboardScreen)
            log_lines = [str(line) for line in app.screen.query_one("#log").lines]
            assert any("discover complete" in line for line in log_lines)

            proxies_table = app.screen.query_one("#proxies", DataTable)
            providers_shown = {proxies_table.get_row_at(i)[0] for i in range(proxies_table.row_count)}
            assert providers_shown == {"shadowsocks-xray", "xray-reality"}

            # There is exactly ONE server in the top-level list, not one
            # per provider.
            await pilot.press("escape")
            await pilot.pause()
            servers_table = app.screen.query_one(DataTable)
            assert servers_table.row_count == 1

    asyncio.run(scenario())


def test_open_proxy_from_dashboard_and_back(isolated_config, monkeypatch):
    """Selecting a row in the dashboard's proxies table (via Enter, once
    the table has focus) opens ProxyDetailScreen for that provider; escape
    returns to the dashboard."""
    remote_files = {"/opt/proxy/shadowsocks-xray/client-info.json": SHADOWSOCKS_XRAY_INFO}
    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(remote_files))
    add_server(ServerProfile(name="node-a", host="203.0.113.10", key_path="/fake/key"))

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ServerDashboardScreen)

            await pilot.click("#discover")
            await pilot.pause(0.5)

            # Buttons come before the DataTable in ServerDashboardScreen's
            # compose(), so they get initial focus - explicitly focus the
            # table so `enter` opens the row instead of re-clicking a button.
            app.screen.query_one("#proxies", DataTable).focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ProxyDetailScreen)
            assert app.screen.provider == "shadowsocks-xray"

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, ServerDashboardScreen)

    asyncio.run(scenario())


def test_verify_without_deployment_reports_nothing_to_verify(isolated_config):
    """Clicking Verify on a proxy that the dashboard knows about (folder
    exists) but that has no local client-info.json (e.g. after Remove
    config) logs "no deployment yet" instead of attempting verification."""
    # A proxy the dashboard knows about (e.g. from a past Discover/Deploy)
    # but whose client-info.json is missing locally right now.
    profile = ServerProfile(name="node-a", host="203.0.113.10", key_path="/fake/key")
    add_server(profile)
    profile.proxy_dir("shadowsocks-xray").mkdir(parents=True)

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ServerDashboardScreen)

            app.screen.query_one("#proxies", DataTable).focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ProxyDetailScreen)

            await pilot.click("#verify")
            await pilot.pause(0.3)

            log_lines = [str(line) for line in app.screen.query_one("#log").lines]
            assert any("no deployment yet" in line for line in log_lines)

    asyncio.run(scenario())


def test_deploy_new_proxy_without_key_prompts_for_password_and_cancel_is_clean(isolated_config):
    """Deploy new proxy on a server with no ssh key configured shows the
    provider/port picker, then a password prompt; cancelling the password
    prompt aborts cleanly and logs a "cancelled" line, with no crash and
    no attempted SSH connection."""
    add_server(ServerProfile(name="node-a", host="203.0.113.10"))

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ServerDashboardScreen)

            await pilot.click("#deploy_new")
            await pilot.pause(0.3)
            await pilot.click("#deploy")  # accept the provider/port picker defaults
            await pilot.pause(0.3)
            assert isinstance(app.screen, PasswordPromptScreen)

            await pilot.click("#cancel")
            await pilot.pause(0.3)
            assert isinstance(app.screen, ServerDashboardScreen)

            log_lines = [str(line) for line in app.screen.query_one("#log").lines]
            assert any("cancelled" in line for line in log_lines)

    asyncio.run(scenario())


def test_device_and_rollback_pickers_dismiss_with_the_selected_name(isolated_config):
    """Choosing a row in a picker returns that row's name (regression: reading
    the name back from the row's Label broke on newer Textual versions)."""
    from ghosty_console.screens.device_picker import DevicePickerScreen
    from ghosty_console.screens.rollback_picker import RollbackPickerScreen

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            chosen = []
            app.push_screen(DevicePickerScreen(["default", "Мой iPhone"]), chosen.append)
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            app.push_screen(RollbackPickerScreen(["20261009T000000Z"]), chosen.append)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert chosen == ["Мой iPhone", "20261009T000000Z"]

    asyncio.run(scenario())


def test_users_window_lists_every_user_and_enter_copies_the_link(isolated_config, monkeypatch):
    """The Devices window shows all users; Enter on a row copies that user's full link."""
    from ghosty_console.screens import devices_list
    from ghosty_console.screens.devices_list import DevicesScreen
    from textual.widgets import Static

    copied = []
    monkeypatch.setattr(devices_list, "copy_text", lambda text: copied.append(text) or True)
    links = [("default", "vless://u-1@203.0.113.7:443?x=1#a"), ("Мой iPhone", "vless://u-2@203.0.113.7:443?x=1#b")]

    async def scenario():
        app = GhostyApp()
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            app.push_screen(DevicesScreen("gmail", links))
            await pilot.pause()
            table = app.screen.query_one("#table", DataTable)
            assert table.row_count == 2
            await pilot.press("down")
            await pilot.pause()
            assert "u-2" in str(app.screen.query_one("#link", Static).render())
            await pilot.press("enter")
            await pilot.pause()
            assert copied == [links[1][1]]
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, DevicesScreen)

    asyncio.run(scenario())
