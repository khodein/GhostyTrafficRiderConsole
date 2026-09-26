from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView


class RollbackPickerScreen(ModalScreen[Optional[str]]):
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
        with Vertical(id="dialog"):
            if self._snapshots:
                yield Label("Pick a snapshot to roll back to:")
                yield ListView(*[ListItem(Label(s)) for s in self._snapshots])
            else:
                yield Label("No snapshots yet - deploy at least once first.")
            yield Button("Cancel", id="cancel")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        label = event.item.query_one(Label)
        self.dismiss(str(label.renderable))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
