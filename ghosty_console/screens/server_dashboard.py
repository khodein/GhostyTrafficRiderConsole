from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, RichLog

from ghosty_console import deploy
from ghosty_console.config import ServerProfile, list_proxies, remove_server
from ghosty_console.screens.deploy_proxy import DeployProxyScreen
from ghosty_console.screens.password_prompt import PasswordPromptScreen
from ghosty_console.screens.proxy_detail import ProxyDetailScreen


class ServerDashboardScreen(Screen):
    """One server: connection details up top, a table of every proxy
    known to be deployed on it, and actions to discover more, deploy a
    new one, or delete the whole server profile."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("b", "back", "Back"),
        Binding("enter", "open_proxy", "Open proxy"),
    ]

    def __init__(self, profile: ServerProfile, auto_discover: bool = False) -> None:
        super().__init__()
        self.profile = profile
        self._auto_discover = auto_discover

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="actions"):
            yield Button("Discover", id="discover", variant="primary")
            yield Button("Deploy new proxy", id="deploy_new")
            yield Button("Delete server", id="delete_server", variant="error")
            yield Button("Back", id="back")
        yield DataTable(id="proxies")
        yield RichLog(id="log", highlight=False, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.profile.name
        self.sub_title = f"{self.profile.user}@{self.profile.host}:{self.profile.port}"
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Provider", "Port", "Domain / site")
        self.action_refresh_proxies()
        self.write_log(f"Selected {self.profile.name} ({self.profile.host})")
        if self._auto_discover:
            self.write_log("[new server - auto-running Discover to see what's already deployed]")
            self._start_password_flow(self.run_discover)

    def on_screen_resume(self) -> None:
        self.action_refresh_proxies()

    def write_log(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def action_refresh_proxies(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for provider in list_proxies(self.profile):
            info = deploy.load_current_client_info(self.profile, provider) or {}
            port = str(info.get("port", "-"))
            extra = info.get("domain") or info.get("site_name") or "-"
            table.add_row(provider, port, extra, key=provider)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_open_proxy(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self.app.push_screen(ProxyDetailScreen(self.profile, str(row_key.value)))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(ProxyDetailScreen(self.profile, str(event.row_key.value)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
            return
        if button_id == "delete_server":
            remove_server(self.profile.name)
            self.app.pop_screen()
            return
        if button_id == "discover":
            self._start_password_flow(self.run_discover)
            return
        if button_id == "deploy_new":
            self._start_deploy_new_flow()
            return

    async def _maybe_prompt_password(self) -> str | None:
        if self.profile.uses_key:
            return None
        return await self.app.push_screen_wait(
            PasswordPromptScreen(f"Password for {self.profile.user}@{self.profile.host}")
        )

    @work()
    async def _start_password_flow(self, worker_fn) -> None:
        password = await self._maybe_prompt_password()
        if password is None and not self.profile.uses_key:
            self.write_log("[cancelled - no password entered]")
            return
        worker_fn(password)

    @work()
    async def _start_deploy_new_flow(self) -> None:
        choice = await self.app.push_screen_wait(DeployProxyScreen())
        if choice is None:
            return
        provider, proxy_port = choice
        password = await self._maybe_prompt_password()
        if password is None and not self.profile.uses_key:
            self.write_log("[cancelled - no password entered]")
            return
        self.run_deploy(provider, proxy_port, password)

    @work(thread=True, exclusive=True, group="ssh")
    def run_deploy(self, provider: str, proxy_port: str, password: str | None) -> None:
        log = lambda line: self.app.call_from_thread(self.write_log, line)
        try:
            info = deploy.deploy(self.profile, provider, proxy_port, password, log)
            details = ", ".join(f"{k}={v}" for k, v in info.items() if k != "provider")
            log(f"[OK] {provider}: {details}")
            self.app.call_from_thread(self.action_refresh_proxies)
        except Exception as exc:
            log(f"[ERROR] {exc}")

    @work(thread=True, exclusive=True, group="ssh")
    def run_discover(self, password: str | None) -> None:
        log = lambda line: self.app.call_from_thread(self.write_log, line)
        try:
            found = deploy.discover(self.profile, password, log)
            if found:
                summary = ", ".join(item["provider"] for item in found)
                log(f"[discover complete] {summary}")
            self.app.call_from_thread(self.action_refresh_proxies)
        except Exception as exc:
            log(f"[ERROR] {exc}")
