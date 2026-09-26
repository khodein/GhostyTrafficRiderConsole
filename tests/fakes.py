"""Reusable SSH double for testing ghosty_console.deploy without a real
server. Swap it in with:

    monkeypatch.setattr(deploy_mod, "SSHSession", make_fake_ssh_session(...))

deploy.py does `from ghosty_console.ssh_client import SSHSession`, binding
the name into its own module namespace - so the class must be patched onto
`ghosty_console.deploy.SSHSession`, not `ghosty_console.ssh_client.SSHSession`.
"""
from __future__ import annotations

import json
from typing import Callable, Optional


def make_fake_ssh_session(
    remote_files: Optional[dict] = None,
    on_command: Optional[Callable[[str, Callable[[str], None]], Optional[int]]] = None,
):
    """Builds a class that stands in for ghosty_console.ssh_client.SSHSession.

    remote_files: maps a remote path (e.g.
        "/opt/proxy/shadowsocks-xray/client-info.json") to a JSON-serializable
        dict - what sftp_get "downloads" from that path. Any key ending in
        client-info.json is also what a `find ... client-info.json`
        exec_stream call (used by discover()) reports as found.
    on_command: optional hook `(command, on_line) -> exit_code | None`, tried
        before the default handling on every exec_stream call; return None to
        fall through to the default (used to simulate install.sh output/
        failure, or to record/assert on the exact commands that were run).
    """
    files = remote_files or {}

    class FakeSSHSession:
        put_files: list[tuple[str, str]] = []

        def __init__(self, profile, password):
            self.profile = profile
            self.password = password

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def exec_stream(self, command: str, on_line) -> int:
            if on_command is not None:
                result = on_command(command, on_line)
                if result is not None:
                    return result
            if command.startswith("find") and "client-info.json" in command:
                for path in files:
                    on_line(path)
                return 0
            # mkdir -p, chmod, the state-file `-printf` listing, docker
            # restart, etc. - harmless no-ops unless on_command intercepts them
            return 0

        def sftp_get(self, remote_path: str, local_path) -> None:
            data = files[remote_path]
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(json.dumps(data))

        def sftp_put(self, local_path, remote_path: str) -> None:
            FakeSSHSession.put_files.append((str(local_path), remote_path))

    return FakeSSHSession
