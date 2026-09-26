from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView


class RollbackPickerScreen(ModalScreen[Optional[str]]):
    """Lets the user pick which past snapshot to roll a proxy back to.

    Args:
        snapshots: Snapshot names to offer, newest-first (as returned by
            config.list_proxy_snapshots()). May be empty.

    Dismisses with:
        The chosen snapshot name, or None if cancelled (or if there was
        nothing to pick from).
    """

    DEFAULT_CSS = """
    RollbackPickerScreen {
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

    def __init__(self, snapshots: list[str]) -> None:
        super().__init__()
        self._snapshots = snapshots

    def compose(self) -> ComposeResult:
        """Builds the list of snapshots (or a fallback message if there are none) + Cancel button."""
        with Vertical(id="dialog"):
            if self._snapshots:
                yield Label("Pick a snapshot to roll back to:")
                yield ListView(*[ListItem(Label(s)) for s in self._snapshots])
            else:
                yield Label("No snapshots yet - deploy at least once first.")
            yield Button("Cancel", id="cancel")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismisses with the snapshot name of the selected list item.

        Args:
            event: The list-selection message; event.item is the selected
                ListItem, whose Label text is the snapshot name.
        """
        label = event.item.query_one(Label)
        self.dismiss(str(label.renderable))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismisses with None - the only button here is Cancel.

        Args:
            event: The button-press message (unused; there's only one button).
        """
        self.dismiss(None)
