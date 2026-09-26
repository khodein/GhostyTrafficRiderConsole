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
    """One SSH connection to a server, used as a context manager.

    Args:
        profile: Server to connect to (host/user/port/key_path).
        password: Password to authenticate with if the profile has no
            key_path configured. Ignored otherwise.
    """

    def __init__(self, profile: ServerProfile, password: str | None = None):
        self.profile = profile
        self.password = password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self, timeout: float = 10.0) -> None:
        """Opens the SSH connection.

        Args:
            timeout: Seconds to wait for the connection before giving up.

        Raises:
            paramiko.SSHException / socket.error: On connection or
                authentication failure (propagated from paramiko).
        """
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
        """Closes the SSH connection."""
        self.client.close()

    def __enter__(self) -> "SSHSession":
        """Connects and returns self, for use in a `with` block."""
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        """Closes the connection when the `with` block exits."""
        self.close()

    def exec_stream(self, command: str, on_line: OnLine) -> int:
        """Runs a command, calling on_line for every output line as it
        arrives, and returns the remote exit status.

        Args:
            command: Shell command to run on the server.
            on_line: Callback invoked once per line of combined
                stdout/stderr (a PTY is allocated, so the two are merged).

        Returns:
            The command's exit status.
        """
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
        """Downloads one file from the server.

        Args:
            remote_path: Absolute path to the file on the server.
            local_path: Where to save it locally. Parent directories are
                created automatically if missing.
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)
        sftp = self.client.open_sftp()
        try:
            sftp.get(remote_path, str(local_path))
        finally:
            sftp.close()

    def sftp_put(self, local_path: Path, remote_path: str) -> None:
        """Uploads one file to the server.

        Args:
            local_path: Local file to upload.
            remote_path: Absolute destination path on the server. Its
                parent directory must already exist.
        """
        sftp = self.client.open_sftp()
        try:
            sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()

    def remote_file_exists(self, remote_path: str) -> bool:
        """Checks whether a file exists on the server.

        Args:
            remote_path: Absolute path to check.

        Returns:
            True if the path exists (as reported by SFTP stat), False
            otherwise.
        """
        sftp = self.client.open_sftp()
        try:
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        finally:
            sftp.close()
