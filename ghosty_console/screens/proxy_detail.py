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
    opening a row in ServerDashboardScreen's proxies table.

    Args:
        profile: The server this proxy is deployed on.
        provider: Provider name of this proxy, e.g. "shadowsocks-xray".
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("b", "back", "Back"),
    ]

    def __init__(self, profile: ServerProfile, provider: str) -> None:
        super().__init__()
        self.profile = profile
        self.provider = provider

    def compose(self) -> ComposeResult:
        """Builds the layout: header, action buttons, log panel, footer."""
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
        """Sets the screen title/subtitle and writes the initial log line."""
        self.title = f"{self.profile.name} / {self.provider}"
        self.sub_title = f"{self.profile.user}@{self.profile.host}:{self.profile.port}"
        self.write_log(f"Selected {self.provider} on {self.profile.name} ({self.profile.host})")

    def write_log(self, line: str) -> None:
        """Appends one line to the on-screen log panel.

        Args:
            line: Text to append.
        """
        self.query_one("#log", RichLog).write(line)

    def action_back(self) -> None:
        """Returns to the server's dashboard."""
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dispatches the action bar's buttons: Back, Delete proxy, Ping,
        Verify, Rollback, Regenerate config, Deploy, Status/Logs, Remove
        config.

        Args:
            event: The button-press message; event.button.id identifies
                which button was clicked.
        """
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
        """Shows the password modal unless this server uses an SSH key.

        Returns:
            The entered password, None if the user cancelled the prompt,
            or None immediately (without prompting) if a key is configured.
        """
        if self.profile.uses_key:
            return None
        return await self.app.push_screen_wait(
            PasswordPromptScreen(f"Password for {self.profile.user}@{self.profile.host}")
        )

    @work()
    async def _start_password_flow(self, worker_fn) -> None:
        """Prompts for a password if needed, then hands off to a worker
        function that performs the actual SSH action.

        Args:
            worker_fn: Callable taking one argument (the password, or None
                if a key is configured) - e.g. self.run_deploy.
        """
        password = await self._maybe_prompt_password()
        if password is None and not self.profile.uses_key:
            self.write_log("[cancelled - no password entered]")
            return
        worker_fn(password)

    @work()
    async def _start_rollback_flow(self) -> None:
        """Shows the snapshot picker, then prompts for a password if
        needed, then starts the rollback worker. Cancelling either step
        aborts cleanly with no side effects."""
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
        """Regenerates immediately (no SSH) if a local client-info.json
        already exists; otherwise prompts for a password first, since
        regenerate_config() will need to fetch it from the server."""
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
        """Background worker: rebuilds this proxy's client profile.

        Args:
            password: SSH password (only used if no local cache exists),
                or None if the server uses a key or a cache exists.
        """
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
        """Background worker: re-runs install.sh for this already-known
        proxy (idempotent - keeps its existing port).

        Args:
            password: SSH password, or None if the server uses a key.
        """
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
        """Background worker: fetches Docker/log/provider-specific status.

        Args:
            password: SSH password, or None if the server uses a key.
        """
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
        """Background worker: stops the container and clears remote state.

        Args:
            password: SSH password, or None if the server uses a key.
        """
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
        """Background worker: restores this proxy to a past snapshot.

        Args:
            password: SSH password, or None if the server uses a key.
            snapshot: Name of the snapshot to restore.
        """
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
        """Background worker: TCP-checks the SSH port and this proxy's port."""
        result = deploy.ping(self.profile, self.provider)
        self.app.call_from_thread(self.write_log, result)

    @work(thread=True, group="verify")
    def run_verify(self) -> None:
        """Background worker: runs the provider's external verify.sh."""
        deploy.verify(
            self.profile, self.provider, lambda line: self.app.call_from_thread(self.write_log, line)
        )
