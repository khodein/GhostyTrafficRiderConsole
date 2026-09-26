"""Thin paramiko wrapper: connect once, stream command output line by line,
and move files over SFTP. All calls are blocking - callers run this inside
a Textual worker thread.
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Callable

import paramiko

from ghosty_console.config import ServerProfile

OnLine = Callable[[str], None]


class SSHSession:
    def __init__(self, profile: ServerProfile, password: str | None = None):
        self.profile = profile
        self.password = password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self, timeout: float = 10.0) -> None:
        kwargs: dict = {
            "hostname": self.profile.host,
            "port": self.profile.port,
            "username": self.profile.user,
            "timeout": timeout,
        }
        if self.profile.uses_key:
            kwargs["key_filename"] = str(Path(self.profile.key_path).expanduser())
        else:
            kwargs["password"] = self.password
        self.client.connect(**kwargs)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "SSHSession":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def exec_stream(self, command: str, on_line: OnLine) -> int:
        """Run a command, calling on_line for every output line as it
        arrives, and return the remote exit status."""
        channel = self.client.get_transport().open_session()
        channel.get_pty()
        channel.exec_command(command)
        channel.settimeout(0.5)

        buffer = ""
        while True:
            try:
                chunk = channel.recv(4096)
                if not chunk:
                    if channel.exit_status_ready():
                        break
                    continue
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    on_line(line.rstrip("\r"))
            except socket.timeout:
                if channel.exit_status_ready():
                    break

        if buffer:
            on_line(buffer.rstrip("\r"))
        return channel.recv_exit_status()

    def sftp_get(self, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        sftp = self.client.open_sftp()
        try:
            sftp.get(remote_path, str(local_path))
        finally:
            sftp.close()

    def sftp_put(self, local_path: Path, remote_path: str) -> None:
        sftp = self.client.open_sftp()
        try:
            sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()

    def remote_file_exists(self, remote_path: str) -> bool:
        sftp = self.client.open_sftp()
        try:
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        finally:
            sftp.close()
