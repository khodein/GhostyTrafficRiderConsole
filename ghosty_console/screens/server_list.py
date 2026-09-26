from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from ghosty_console.config import add_server, load_servers, remove_server
from ghosty_console.screens.add_server import AddServerScreen
from ghosty_console.screens.server_dashboard import ServerDashboardScreen


class ServerListScreen(Screen):
    """Top-level screen: every known server, one row each. The app's
    starting screen (see GhostyApp.on_mount)."""

    BINDINGS = [
        Binding("a", "add_server", "Add server"),
        Binding("d", "delete_server", "Delete selected"),
        Binding("enter", "open_server", "Open"),
        Binding("r", "refresh_servers", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        """Builds the layout: header, the servers table, footer (key bindings hint bar)."""
        yield Header()
        yield DataTable(id="servers")
        yield Footer()

    def on_mount(self) -> None:
        """Sets up the table's columns and populates its first rows."""
        self.title = "Ghosty Traffic Rider Console"
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Host", "User", "Auth")
        self.action_refresh_servers()

    def on_screen_resume(self) -> None:
        """Refreshes the table when returning here from a server's
        dashboard (e.g. after Delete server was used there)."""
        self.action_refresh_servers()

    def action_refresh_servers(self) -> None:
        """Reloads server profiles from disk and redraws the table."""
        table = self.query_one(DataTable)
        table.clear()
        for profile in load_servers():
            auth = f"key: {profile.key_path}" if profile.uses_key else "password prompt"
            table.add_row(profile.name, profile.host, profile.user, auth, key=profile.name)

    @work()
    async def action_add_server(self) -> None:
        """Opens the Add server modal; on success, saves the new profile,
        refreshes the table, and jumps straight into its dashboard with
        auto_discover=True so its already-deployed proxies (if any) show
        up immediately without a manual Discover click."""
        profile = await self.app.push_screen_wait(AddServerScreen())
        if profile is not None:
            add_server(profile)
            self.action_refresh_servers()
            self.app.push_screen(ServerDashboardScreen(profile, auto_discover=True))

    def action_delete_server(self) -> None:
        """Deletes the currently selected server (and all its local proxy
        state) after confirming a row is selected. Purely local - the
        actual VPS is left untouched."""
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        remove_server(str(row_key.value))
        self.action_refresh_servers()

    def action_open_server(self) -> None:
        """Opens the dashboard for the currently selected server (keyboard path)."""
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        name = str(row_key.value)
        profile = next((p for p in load_servers() if p.name == name), None)
        if profile is not None:
            self.app.push_screen(ServerDashboardScreen(profile))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Opens the dashboard for the clicked/selected server (mouse/Enter path).

        Args:
            event: The row-selection message; event.row_key.value is the
                server's name (used as the table's row key).
        """
        name = str(event.row_key.value)
        profile = next((p for p in load_servers() if p.name == name), None)
        if profile is not None:
            self.app.push_screen(ServerDashboardScreen(profile))
