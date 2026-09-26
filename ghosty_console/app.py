from textual.app import App

from ghosty_console.screens.server_list import ServerListScreen


class GhostyApp(App):
    TITLE = "Ghosty Traffic Rider Console"
    BINDINGS = [("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.push_screen(ServerListScreen())


def run() -> None:
    GhostyApp().run()
