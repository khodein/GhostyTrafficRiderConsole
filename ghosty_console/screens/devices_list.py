from __future__ import annotations

import shutil
import subprocess

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label, Static

LINK_PREVIEW_LEN = 56


def copy_text(text: str) -> bool:
    """Puts text on the system clipboard.

    Uses pbcopy on macOS (works in any terminal); otherwise falls back to the
    terminal's OSC 52 clipboard escape, which not every terminal supports.

    Args:
        text: Text to copy.

    Returns:
        True if pbcopy copied it; False if only the OSC 52 fallback was
        attempted (copy may not have happened).
    """
    pbcopy = shutil.which("pbcopy")
    if pbcopy:
        try:
            subprocess.run([pbcopy], input=text.encode(), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            pass
    return False


class DevicesScreen(ModalScreen[None]):
    """Lists every user (device) of a proxy with its connection link.
    Highlighting a row shows the full link; pressing Enter (or clicking) a
    row copies that link to the clipboard.

    Args:
        server_name: The server's name in the console, shown in the title.
        links: (user name, share link) pairs, e.g. from deploy.list_device_links().
    """

    DEFAULT_CSS = """
    DevicesScreen {
        align: center middle;
    }
    #dialog {
        width: 96;
        height: auto;
        max-height: 32;
        border: heavy $accent;
        padding: 1 2;
    }
    #table {
        height: auto;
        max-height: 12;
    }
    #link {
        margin-top: 1;
        height: auto;
        max-height: 8;
    }
    """

    def __init__(self, server_name: str, links: list[tuple[str, str]]) -> None:
        super().__init__()
        self._server_name = server_name
        self._links = dict(links)
        self._order = [name for name, _ in links]

    def compose(self) -> ComposeResult:
        """Builds the modal: title, users table, full-link box, status line, Close button."""
        with Vertical(id="dialog"):
            yield Label(f"Users of {self._server_name} ({len(self._order)}) - Enter copies the link")
            yield DataTable(id="table", cursor_type="row")
            yield Static("", id="link", markup=False)
            yield Label("", id="status")
            yield Button("Close", id="close")

    def on_mount(self) -> None:
        """Fills the table and focuses it, previewing the first user's link."""
        table = self.query_one("#table", DataTable)
        table.add_columns("User", "Link")
        for name in self._order:
            link = self._links[name]
            preview = link if len(link) <= LINK_PREVIEW_LEN else link[:LINK_PREVIEW_LEN] + "…"
            table.add_row(name, preview, key=name)
        table.focus()
        if self._order:
            self.query_one("#link", Static).update(self._links[self._order[0]])

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Shows the full link of the highlighted user.

        Args:
            event: The highlight message; event.row_key.value is the user name.
        """
        name = event.row_key.value
        if name in self._links:
            self.query_one("#link", Static).update(self._links[name])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Copies the selected user's link to the clipboard and reports it.

        Args:
            event: The selection message; event.row_key.value is the user name.
        """
        name = event.row_key.value
        link = self._links.get(name)
        if link is None:
            return
        status = self.query_one("#status", Label)
        if copy_text(link):
            status.update(f"Copied the link of '{name}' to the clipboard")
        else:
            self.app.copy_to_clipboard(link)
            status.update(f"Link of '{name}' sent to the terminal clipboard - if it did not copy, select it above")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Closes the window - the only button here is Close.

        Args:
            event: The button-press message (unused; there's only one button).
        """
        self.dismiss(None)

    def key_escape(self) -> None:
        """Closes the window on Escape."""
        self.dismiss(None)
