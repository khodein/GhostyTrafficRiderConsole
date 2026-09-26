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
    BINDINGS = [
        Binding("a", "add_server", "Add server"),
        Binding("d", "delete_server", "Delete selected"),
        Binding("enter", "open_server", "Open"),
        Binding("r", "refresh_servers", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="servers")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Ghosty Traffic Rider Console"
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Host", "User", "Auth")
        self.action_refresh_servers()

    def on_screen_resume(self) -> None:
        # Returning from a server's dashboard - refresh in case anything
        # changed (e.g. Delete server was used there).
        self.action_refresh_servers()

    def action_refresh_servers(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for profile in load_servers():
            auth = f"key: {profile.key_path}" if profile.uses_key else "password prompt"
            table.add_row(profile.name, profile.host, profile.user, auth, key=profile.name)

    @work()
    async def action_add_server(self) -> None:
        profile = await self.app.push_screen_wait(AddServerScreen())
        if profile is not None:
            add_server(profile)
            self.action_refresh_servers()
            # Jump straight into the new server and scan it for anything
            # already deployed there, instead of making the user open it
            # and press Discover manually every time.
            self.app.push_screen(ServerDashboardScreen(profile, auto_discover=True))

    def action_delete_server(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        remove_server(str(row_key.value))
        self.action_refresh_servers()

    def action_open_server(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        name = str(row_key.value)
        profile = next((p for p in load_servers() if p.name == name), None)
        if profile is not None:
            self.app.push_screen(ServerDashboardScreen(profile))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        name = str(event.row_key.value)
        profile = next((p for p in load_servers() if p.name == name), None)
        if profile is not None:
            self.app.push_screen(ServerDashboardScreen(profile))
