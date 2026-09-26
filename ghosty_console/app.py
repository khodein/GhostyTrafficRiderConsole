from textual.app import App

from ghosty_console.screens.server_list import ServerListScreen


class GhostyApp(App):
    """The TUI application. Owns no state of its own - everything lives in
    ghosty_console.config (on disk) and is navigated via the screen stack
    starting from ServerListScreen."""

    TITLE = "Ghosty Traffic Rider Console"
    BINDINGS = [("q", "quit", "Quit")]

    def on_mount(self) -> None:
        """Pushes the initial screen (the server list) once the app starts."""
        self.push_screen(ServerListScreen())


def run() -> None:
    """Entry point: creates and runs the app. Blocks until the user quits."""
    GhostyApp().run()
