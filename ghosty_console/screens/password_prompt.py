from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class PasswordPromptScreen(ModalScreen[Optional[str]]):
    """Asks for a password once, in memory only, never written to disk.

    Args:
        prompt: Label text shown above the input, e.g.
            "Password for root@1.2.3.4".

    Dismisses with:
        The entered password (str), or None if the user cancelled.
    """

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
        """Builds the modal: prompt label, password input, Connect/Cancel buttons."""
        with Vertical(id="dialog"):
            yield Label(self._prompt)
            yield Input(placeholder="password", password=True, id="password")
            with Vertical():
                yield Button("Connect", variant="primary", id="connect")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismisses with the entered password on Connect, or None on Cancel.

        Args:
            event: The button-press message; event.button.id identifies
                which button was clicked ("connect" or "cancel").
        """
        if event.button.id == "connect":
            self.dismiss(self.query_one("#password", Input).value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Lets pressing Enter in the password field submit it directly.

        Args:
            event: The input-submitted message; event.value is the text
                entered.
        """
        self.dismiss(event.value)
