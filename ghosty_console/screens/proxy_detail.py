from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog

from ghosty_console import deploy
from ghosty_console.config import ServerProfile, list_proxy_snapshots, remove_proxy
from ghosty_console.screens.password_prompt import PasswordPromptScreen
from ghosty_console.screens.rollback_picker import RollbackPickerScreen


class ProxyDetailScreen(Screen):
    """Actions for one proxy (provider) deployed on a server. Reached by
    opening a row in ServerDashboardScreen's proxies table."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("b", "back", "Back"),
    ]

    def __init__(self, profile: ServerProfile, provider: str) -> None:
        super().__init__()
        self.profile = profile
        self.provider = provider

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="actions"):
            yield Button("Deploy", id="deploy", variant="primary")
            yield Button("Regenerate config", id="regenerate")
            yield Button("Ping", id="ping")
            yield Button("Verify", id="verify")
            yield Button("Status / Logs", id="status")
            yield Button("Rollback", id="rollback")
            yield Button("Remove config", id="remove", variant="warning")
            yield Button("Delete proxy", id="delete_proxy", variant="error")
            yield Button("Back", id="back")
        yield RichLog(id="log", highlight=False, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"{self.profile.name} / {self.provider}"
        self.sub_title = f"{self.profile.user}@{self.profile.host}:{self.profile.port}"
        self.write_log(f"Selected {self.provider} on {self.profile.name} ({self.profile.host})")

    def write_log(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
            return
        if button_id == "delete_proxy":
            remove_proxy(self.profile, self.provider)
            self.app.pop_screen()
            return
        if button_id == "ping":
            self.run_ping()
            return
        if button_id == "verify":
            self.run_verify()
            return
        if button_id == "rollback":
            self._start_rollback_flow()
            return
        if button_id == "regenerate":
            self._start_regenerate_flow()
            return
        if button_id == "deploy":
            self._start_password_flow(self.run_deploy)
        elif button_id == "status":
            self._start_password_flow(self.run_status)
        elif button_id == "remove":
            self._start_password_flow(self.run_remove)

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
    async def _start_rollback_flow(self) -> None:
        snapshots = list_proxy_snapshots(self.profile, self.provider)
        chosen = await self.app.push_screen_wait(RollbackPickerScreen(snapshots))
        if not chosen:
            return
        password = await self._maybe_prompt_password()
        if password is None and not self.profile.uses_key:
            return
        self.run_rollback(password, chosen)

    @work()
    async def _start_regenerate_flow(self) -> None:
        info_file = self.profile.proxy_current_dir(self.provider) / "client-info.json"
        if info_file.exists():
            self.run_regenerate(None)
            return
        password = await self._maybe_prompt_password()
        if password is None and not self.profile.uses_key:
            self.write_log("[cancelled - no password entered]")
            return
        self.run_regenerate(password)

    @work(thread=True, exclusive=True, group="ssh")
    def run_regenerate(self, password: str | None) -> None:
        try:
            path = deploy.regenerate_config(
                self.profile,
                self.provider,
                password,
                lambda line: self.app.call_from_thread(self.write_log, line),
            )
            self.app.call_from_thread(
                self.write_log, f"[OK] client-info at {path}, profile written to proxy-scripts/output/"
            )
        except Exception as exc:
            self.app.call_from_thread(self.write_log, f"[ERROR] {exc}")

    @work(thread=True, exclusive=True, group="ssh")
    def run_deploy(self, password: str | None) -> None:
        try:
            info = deploy.deploy(
                self.profile,
                self.provider,
                "",  # redeploy - install.sh keeps the existing port either way
                password,
                lambda line: self.app.call_from_thread(self.write_log, line),
            )
            details = ", ".join(f"{k}={v}" for k, v in info.items() if k != "provider")
            self.app.call_from_thread(self.write_log, f"[OK] {details}")
        except Exception as exc:
            self.app.call_from_thread(self.write_log, f"[ERROR] {exc}")

    @work(thread=True, exclusive=True, group="ssh")
    def run_status(self, password: str | None) -> None:
        try:
            deploy.fetch_status(
                self.profile,
                self.provider,
                password,
                lambda line: self.app.call_from_thread(self.write_log, line),
            )
        except Exception as exc:
            self.app.call_from_thread(self.write_log, f"[ERROR] {exc}")

    @work(thread=True, exclusive=True, group="ssh")
    def run_remove(self, password: str | None) -> None:
        try:
            deploy.remove_config(
                self.profile,
                self.provider,
                password,
                lambda line: self.app.call_from_thread(self.write_log, line),
            )
        except Exception as exc:
            self.app.call_from_thread(self.write_log, f"[ERROR] {exc}")

    @work(thread=True, exclusive=True, group="ssh")
    def run_rollback(self, password: str | None, snapshot: str) -> None:
        try:
            deploy.rollback(
                self.profile,
                self.provider,
                password,
                snapshot,
                lambda line: self.app.call_from_thread(self.write_log, line),
            )
        except Exception as exc:
            self.app.call_from_thread(self.write_log, f"[ERROR] {exc}")

    @work(thread=True, group="ping")
    def run_ping(self) -> None:
        result = deploy.ping(self.profile, self.provider)
        self.app.call_from_thread(self.write_log, result)

    @work(thread=True, group="verify")
    def run_verify(self) -> None:
        deploy.verify(
            self.profile, self.provider, lambda line: self.app.call_from_thread(self.write_log, line)
        )
