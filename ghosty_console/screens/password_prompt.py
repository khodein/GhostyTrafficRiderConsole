from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class PasswordPromptScreen(ModalScreen[Optional[str]]):
    """Asks for a password once, in memory only, never written to disk."""

    DEFAULT_CSS = """
    PasswordPromptScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
    }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt)
            yield Input(placeholder="password", password=True, id="password")
            with Vertical():
                yield Button("Connect", variant="primary", id="connect")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect":
            self.dismiss(self.query_one("#password", Input).value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)
