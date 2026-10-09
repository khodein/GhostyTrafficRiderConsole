from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ghosty_console.deploy import DEVICE_NAME_RE


class DeviceNamePromptScreen(ModalScreen[Optional[str]]):
    """Asks for a device name (e.g. "My iPhone"), which becomes part of its
    share link's title ("<server> · <device>").

    Args:
        title: Prompt shown above the input.
        button: Label of the confirm button.
        initial: Pre-filled input value (e.g. the current name when renaming).

    Dismisses with:
        The valid device name (str), or None if the user cancelled.
    """

    DEFAULT_CSS = """
    DeviceNamePromptScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
    }
    """

    def __init__(self, title: str = "Device name (up to 32 chars)", button: str = "Add", initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._button = button
        self._initial = initial

    def compose(self) -> ComposeResult:
        """Builds the modal: label, name input, error label, confirm/Cancel buttons."""
        with Vertical(id="dialog"):
            yield Label(self._title)
            yield Input(value=self._initial, placeholder="My iPhone", id="name")
            yield Label("", id="error")
            with Vertical():
                yield Button(self._button, variant="primary", id="add")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Validates and dismisses with the name on Add, or None on Cancel.

        Args:
            event: The button-press message; event.button.id identifies
                which button was clicked ("add" = confirm, or "cancel").
        """
        if event.button.id == "add":
            self._submit(self.query_one("#name", Input).value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Lets pressing Enter in the name field submit it directly.

        Args:
            event: The input-submitted message; event.value is the text entered.
        """
        self._submit(event.value)

    def _submit(self, value: str) -> None:
        """Dismisses with the trimmed name if valid; otherwise shows an error.

        Args:
            value: Raw text from the name input.
        """
        name = value.strip()
        if DEVICE_NAME_RE.match(name):
            self.dismiss(name)
        else:
            self.query_one("#error", Label).update("Invalid name - letters, digits, space, _ - . (max 32)")
