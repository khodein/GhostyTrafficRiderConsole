from __future__ import annotations

from typing import Optional, Tuple

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from ghosty_console.config import list_providers


class DeployProxyScreen(ModalScreen[Optional[Tuple[str, str]]]):
    """Picks a provider + optional port for a new proxy on an already-known
    server.

    Dismisses with:
        A (provider, proxy_port) tuple - proxy_port is an empty string if
        left blank, meaning "let install.sh pick a random port" - or None
        if cancelled.
    """

    DEFAULT_CSS = """
    DeployProxyScreen {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
    }
    #dialog Input {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Builds the form: provider select, optional-port input, Deploy/Cancel buttons."""
        providers = list_providers() or ["shadowsocks-xray"]
        with Vertical(id="dialog"):
            yield Label("Deploy a new proxy on this server")
            yield Select[str](
                [(p, p) for p in providers], value=providers[0], id="provider", allow_blank=False
            )
            yield Input(placeholder="proxy port (leave empty for random, first install only)", id="proxy_port")
            with Vertical():
                yield Button("Deploy", variant="primary", id="deploy")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Validates the port field and dismisses with (provider, proxy_port)
        on Deploy, or with None on Cancel (or on a validation failure,
        after ringing the terminal bell).

        Args:
            event: The button-press message; event.button.id identifies
                which button was clicked ("deploy" or "cancel").
        """
        if event.button.id != "deploy":
            self.dismiss(None)
            return

        provider = str(self.query_one("#provider", Select).value)
        proxy_port = self.query_one("#proxy_port", Input).value.strip()

        if proxy_port and not proxy_port.isdigit():
            self.app.bell()
            return

        self.dismiss((provider, proxy_port))
