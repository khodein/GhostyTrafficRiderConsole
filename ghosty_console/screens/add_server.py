from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ghosty_console.config import ServerProfile


class AddServerScreen(ModalScreen[Optional[ServerProfile]]):
    """Just the SSH connection details - no provider/port here. What's
    already deployed there gets discovered right after saving (see
    ServerListScreen.action_add_server), and new proxies are added from
    inside the server's dashboard via Deploy new proxy."""

    DEFAULT_CSS = """
    AddServerScreen {
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
        with Vertical(id="dialog"):
            yield Label("Add server")
            yield Input(placeholder="name (e.g. nl-1)", id="name")
            yield Input(placeholder="host / IP", id="host")
            yield Input(placeholder="ssh user", value="root", id="user")
            yield Input(placeholder="ssh port", value="22", id="port")
            yield Input(placeholder="ssh key path (leave empty to use a password each time)", id="key_path")
            with Vertical():
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return

        name = self.query_one("#name", Input).value.strip()
        host = self.query_one("#host", Input).value.strip()
        user = self.query_one("#user", Input).value.strip() or "root"
        port_text = self.query_one("#port", Input).value.strip() or "22"
        key_path = self.query_one("#key_path", Input).value.strip()

        if not name or not host:
            self.app.bell()
            return

        try:
            port = int(port_text)
        except ValueError:
            self.app.bell()
            return

        self.dismiss(ServerProfile(name=name, host=host, user=user, port=port, key_path=key_path))
