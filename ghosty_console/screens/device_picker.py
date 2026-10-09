from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView


class DevicePickerScreen(ModalScreen[Optional[str]]):
    """Lets the user pick one of the proxy's devices (to remove or rename).

    Args:
        devices: Device names to offer (from deploy.list_devices()). May be empty.
        title: Prompt shown above the list.

    Dismisses with:
        The chosen device name, or None if cancelled (or if there was
        nothing to pick from).
    """

    DEFAULT_CSS = """
    DevicePickerScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        max-height: 20;
        border: heavy $accent;
        padding: 1 2;
    }
    """

    def __init__(self, devices: list[str], title: str = "Pick a device:") -> None:
        super().__init__()
        self._devices = devices
        self._title = title

    def compose(self) -> ComposeResult:
        """Builds the list of devices (or a fallback message if there are none) + Cancel button."""
        with Vertical(id="dialog"):
            if self._devices:
                yield Label(self._title)
                yield ListView(*[ListItem(Label(d), name=d) for d in self._devices])
            else:
                yield Label("No devices yet - deploy or Regenerate config first.")
            yield Button("Cancel", id="cancel")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismisses with the name of the selected list item.

        Args:
            event: The list-selection message; event.item is the selected
                ListItem, whose name is the device name.
        """
        self.dismiss(event.item.name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismisses with None - the only button here is Cancel.

        Args:
            event: The button-press message (unused; there's only one button).
        """
        self.dismiss(None)
