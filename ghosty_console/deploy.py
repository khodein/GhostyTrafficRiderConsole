"""Actions available for a server's proxies: deploy, discover, regenerate
config, ping, verify, status/logs, rollback, remove. Provider-agnostic:
everything provider-specific (what to install, how to build a client
profile, how to verify it) lives in proxy-scripts/providers/<provider>/ and
is driven from here by name only. A server can have several proxies
(one per provider) - every function below takes the provider explicitly
except discover(), which finds all of them at once. Each function is
blocking and meant to run inside a Textual worker thread; progress is
reported through an on_line(str) callback.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

from ghosty_console.config import PROXY_SCRIPTS_DIR, ServerProfile, new_proxy_snapshot_dir
from ghosty_console.ssh_client import SSHSession, OnLine

REMOTE_SCRIPTS_ROOT = "/opt/proxy-scripts"
REMOTE_STATE_ROOT = "/opt/proxy"


def _provider_dir(provider: str) -> Path:
    """Local path to a provider's scripts.

    Args:
        provider: Provider name, e.g. "shadowsocks-xray".

    Returns:
        proxy-scripts/providers/<provider>/ on this machine.
    """
    return PROXY_SCRIPTS_DIR / "providers" / provider


def _remote_scripts_dir(provider: str) -> str:
    """Where this provider's scripts get uploaded to on the VPS.

    Args:
        provider: Provider name, e.g. "shadowsocks-xray".

    Returns:
        Remote path string, e.g. "/opt/proxy-scripts/shadowsocks-xray".
    """
    return f"{REMOTE_SCRIPTS_ROOT}/{provider}"


def _remote_state_dir(provider: str) -> str:
    """Where this provider's install.sh writes its state on the VPS
    (client-info.json, certs, etc.).

    Args:
        provider: Provider name, e.g. "shadowsocks-xray".

    Returns:
        Remote path string, e.g. "/opt/proxy/shadowsocks-xray".
    """
    return f"{REMOTE_STATE_ROOT}/{provider}"


def deploy(
    profile: ServerProfile, provider: str, proxy_port: str, password: str | None, on_line: OnLine
) -> dict:
    """Installs (or re-installs) one proxy on a server over SSH.

    Uploads the provider's remote/ scripts, runs install.sh, then pulls
    the resulting client-info.json (and any other state files) back down
    into a fresh local snapshot and promotes it to current/.

    Args:
        profile: Server to connect to.
        provider: Provider to install, e.g. "shadowsocks-xray".
        proxy_port: Port to request via the PROXY_PORT env var on first
            install; empty string lets install.sh pick a random one. Has
            no effect on a re-deploy of an already-installed proxy (the
            server keeps whatever port it originally picked).
        password: SSH password, or None if the server uses a key.
        on_line: Callback invoked with each line of progress/output.

    Returns:
        The parsed client-info.json produced by install.sh.

    Raises:
        RuntimeError: If install.sh exits with a non-zero status.
    """
    provider_dir = _provider_dir(provider)
    remote_dir = _remote_scripts_dir(provider)
    state_dir = _remote_state_dir(provider)

    with SSHSession(profile, password) as ssh:
        on_line(f"[connected to {profile.host}]")

        ssh.exec_stream(f"mkdir -p {remote_dir}", on_line)
        for f in sorted((provider_dir / "remote").iterdir()):
            if f.is_file():
                ssh.sftp_put(f, f"{remote_dir}/{f.name}")

        port_env = f"PROXY_PORT={proxy_port} " if proxy_port else ""
        command = (
            f"chmod +x {remote_dir}/*.sh 2>/dev/null; "
            f"SERVER_IP={profile.host} {port_env}{remote_dir}/install.sh"
        )
        status = ssh.exec_stream(command, on_line)
        if status != 0:
            raise RuntimeError(f"remote install.sh exited with status {status}")

        client_info = _sync_proxy_state(ssh, profile, provider, state_dir, on_line)

    on_line("[deployed]")
    return client_info


def discover(profile: ServerProfile, password: str | None, on_line: OnLine) -> list[dict]:
    """Scans the server for anything already deployed by any provider's
    install.sh (i.e. anything with an /opt/proxy/<provider>/client-info.json)
    and pulls each one's state down under this server's proxies/ - so every
    action becomes available immediately from this device, regardless of
    which device originally ran Deploy.

    Args:
        profile: Server to connect to and scan.
        password: SSH password, or None if the server uses a key.
        on_line: Callback invoked with each line of progress/output.

    Returns:
        One dict per proxy found, each with "provider" (name) and "info"
        (its parsed client-info.json). Empty list if nothing was found.
    """
    found: list[dict] = []
    with SSHSession(profile, password) as ssh:
        on_line(f"[connected to {profile.host}, scanning {REMOTE_STATE_ROOT}]")

        listing: list[str] = []
        ssh.exec_stream(
            f"find {REMOTE_STATE_ROOT} -maxdepth 2 -name client-info.json 2>/dev/null || true",
            listing.append,
        )
        remote_paths = [p.strip() for p in listing if p.strip()]

        if not remote_paths:
            on_line("[nothing deployed by this tool found on the server]")
            return found

        on_line(f"[found {len(remote_paths)} deployed provider(s)]")
        for remote_path in remote_paths:
            state_dir = remote_path.rsplit("/", 1)[0]
            provider = state_dir.rsplit("/", 1)[-1]

            on_line(f"[syncing {provider}]")
            client_info = _sync_proxy_state(ssh, profile, provider, state_dir, on_line)
            found.append({"provider": provider, "info": client_info})

    return found


def _sync_proxy_state(
    ssh: SSHSession, profile: ServerProfile, provider: str, state_dir: str, on_line: OnLine
) -> dict:
    """Pulls client-info.json + every other state file under state_dir into
    a fresh local snapshot for this server's <provider> proxy, regenerates
    its client config profile, and promotes the snapshot to current/.

    Shared building block used by deploy(), discover(), regenerate_config()
    and rollback() - anywhere state needs to be pulled from the server and
    made "current" locally.

    Args:
        ssh: Already-connected SSH session to the server.
        profile: Server the proxy belongs to.
        provider: Provider name of the proxy being synced.
        state_dir: Remote directory holding this proxy's client-info.json
            and other state files, e.g. "/opt/proxy/shadowsocks-xray".
        on_line: Callback invoked with each line of progress/output.

    Returns:
        The parsed client-info.json that was pulled down.
    """
    snapshot = new_proxy_snapshot_dir(profile, provider)
    ssh.sftp_get(f"{state_dir}/client-info.json", snapshot / "client-info.json")
    _snapshot_remote_state(ssh, state_dir, snapshot)

    client_info = json.loads((snapshot / "client-info.json").read_text())
    _generate_client_profile(snapshot / "client-info.json", on_line)
    _promote_to_current(profile, provider, snapshot)
    return client_info


def _snapshot_remote_state(ssh: SSHSession, state_dir: str, snapshot: Path) -> None:
    """Copies every plain file directly under state_dir (skipping
    subdirectories like certs/ or build/) so rollback can push the same
    files back later, regardless of which provider they belong to.

    client-info.json itself is skipped here since callers fetch it
    separately (it's the one file every provider is guaranteed to have).

    Args:
        ssh: Already-connected SSH session to the server.
        state_dir: Remote directory to copy files from.
        snapshot: Local directory to copy files into (already created).
    """
    listing = []
    ssh.exec_stream(
        f"find {state_dir} -maxdepth 1 -type f -printf '%f\\n' 2>/dev/null || true",
        listing.append,
    )
    for name in listing:
        name = name.strip()
        if not name or name == "client-info.json":
            continue
        try:
            ssh.sftp_get(f"{state_dir}/{name}", snapshot / name)
        except OSError:
            pass


def _generate_client_profile(client_info_file: Path, on_line: OnLine) -> None:
    """Runs proxy-scripts/generate-config.sh against a client-info.json to
    (re)build the client-facing profile (Clash YAML / share link) in
    proxy-scripts/output/.

    Args:
        client_info_file: Path to the client-info.json to generate from.
        on_line: Callback invoked with each line of the script's stdout
            (and stderr, if it fails).

    Raises:
        RuntimeError: If generate-config.sh exits with a non-zero status.
    """
    result = subprocess.run(
        [str(PROXY_SCRIPTS_DIR / "generate-config.sh"), str(client_info_file)],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        on_line(line)
    if result.returncode != 0:
        for line in result.stderr.splitlines():
            on_line(line)
        raise RuntimeError("generate-config.sh failed")


def _promote_to_current(profile: ServerProfile, provider: str, snapshot: Path) -> None:
    """Replaces a proxy's current/ directory with the contents of a snapshot.

    Args:
        profile: Server the proxy belongs to.
        provider: Provider name of the proxy being promoted.
        snapshot: Snapshot directory (under history/) to copy into current/.
    """
    current = profile.proxy_current_dir(provider)
    if current.exists():
        shutil.rmtree(current)
    shutil.copytree(snapshot, current)


def load_current_client_info(profile: ServerProfile, provider: str) -> dict | None:
    """Reads the locally cached client-info.json for one proxy, if any.

    Args:
        profile: Server the proxy belongs to.
        provider: Provider name of the proxy to look up.

    Returns:
        The parsed client-info.json, or None if this proxy has no
        current/ state locally (never deployed/discovered from this
        device, or Remove config was run).
    """
    info_file = profile.proxy_current_dir(provider) / "client-info.json"
    if not info_file.exists():
        return None
    return json.loads(info_file.read_text())


def ping(profile: ServerProfile, provider: str | None = None) -> str:
    """Checks TCP reachability of a server's SSH port and, optionally, one
    of its proxy's ports - without opening a real SSH session.

    Args:
        profile: Server to check.
        provider: If given, also checks this proxy's port (read from its
            locally cached client-info.json). If omitted, or if there's no
            cached info for it, only the SSH port is checked.

    Returns:
        Human-readable multi-line report, one line per port checked.
    """
    lines = []
    started = time.monotonic()
    try:
        with socket.create_connection((profile.host, profile.port), timeout=5):
            elapsed_ms = (time.monotonic() - started) * 1000
            lines.append(f"SSH port {profile.port}: reachable, {elapsed_ms:.0f} ms")
    except OSError as exc:
        lines.append(f"SSH port {profile.port}: unreachable ({exc})")

    if provider:
        client_info = load_current_client_info(profile, provider)
        if client_info and "port" in client_info:
            proxy_port = client_info["port"]
            started = time.monotonic()
            try:
                with socket.create_connection((profile.host, proxy_port), timeout=5):
                    elapsed_ms = (time.monotonic() - started) * 1000
                    lines.append(f"Proxy port {proxy_port}: reachable, {elapsed_ms:.0f} ms")
            except OSError as exc:
                lines.append(f"Proxy port {proxy_port}: unreachable ({exc})")
    return "\n".join(lines)


def fetch_status(profile: ServerProfile, provider: str, password: str | None, on_line: OnLine) -> None:
    """Fetches a proxy's Docker container status, recent logs, and any
    provider-specific extra status info (e.g. cert renewal timer state)
    over SSH.

    Args:
        profile: Server to connect to.
        provider: Provider name of the proxy to inspect; also the expected
            Docker container name.
        password: SSH password, or None if the server uses a key.
        on_line: Callback invoked with each line of output.
    """
    provider_dir = _provider_dir(provider)
    remote_dir = _remote_scripts_dir(provider)
    has_status_extra = (provider_dir / "remote" / "status-extra.sh").exists()

    with SSHSession(profile, password) as ssh:
        ssh.exec_stream(
            f"echo '--- docker ---'; "
            f"docker ps --filter name={provider} --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}'; "
            f"echo '--- last 100 log lines ---'; "
            f"docker logs {provider} --tail 100 2>&1",
            on_line,
        )
        if has_status_extra:
            ssh.exec_stream(
                f"SERVER_IP={profile.host} {remote_dir}/status-extra.sh 2>&1", on_line
            )


def rollback(
    profile: ServerProfile, provider: str, password: str | None, snapshot_name: str, on_line: OnLine
) -> dict:
    """Restores a proxy to a previously saved snapshot.

    Pushes the snapshot's state files back to the server and restarts the
    proxy's Docker container so it picks them up, then promotes the same
    snapshot to current/ locally.

    Args:
        profile: Server to connect to.
        provider: Provider name of the proxy to roll back.
        password: SSH password, or None if the server uses a key.
        snapshot_name: Name of the snapshot (from list_proxy_snapshots())
            to restore.
        on_line: Callback invoked with each line of progress/output.

    Returns:
        The parsed client-info.json from the restored snapshot.

    Raises:
        FileNotFoundError: If the named snapshot has no client-info.json
            (doesn't exist, or is corrupt).
        RuntimeError: If restarting the Docker container fails.
    """
    snapshot = profile.proxy_history_dir(provider) / snapshot_name
    info_file = snapshot / "client-info.json"
    if not info_file.exists():
        raise FileNotFoundError(f"snapshot {snapshot_name} has no client-info.json")

    state_dir = _remote_state_dir(provider)

    with SSHSession(profile, password) as ssh:
        on_line(f"[rolling back to {snapshot_name}]")
        for f in sorted(snapshot.iterdir()):
            if f.is_file():
                ssh.sftp_put(f, f"{state_dir}/{f.name}")
        status = ssh.exec_stream(f"docker restart {provider}", on_line)
        if status != 0:
            raise RuntimeError(f"container restart exited with status {status}")

    _generate_client_profile(info_file, on_line)
    _promote_to_current(profile, provider, snapshot)
    on_line(f"[rollback complete, now running {snapshot_name}]")
    return json.loads(info_file.read_text())


def remove_config(profile: ServerProfile, provider: str, password: str | None, on_line: OnLine) -> None:
    """Stops and removes a proxy's Docker container and clears its remote
    state directory (but leaves TLS certificates and renewal timers, if
    any, untouched).

    Locally, current/ is emptied (but recreated) - the proxy stays known
    (with its history intact) until Delete proxy is used explicitly.

    Args:
        profile: Server to connect to.
        provider: Provider name of the proxy to remove.
        password: SSH password, or None if the server uses a key.
        on_line: Callback invoked with each line of progress/output.
    """
    state_dir = _remote_state_dir(provider)
    with SSHSession(profile, password) as ssh:
        on_line("[stopping and removing remote proxy config]")
        ssh.exec_stream(
            f"docker rm -f {provider} 2>/dev/null || true; "
            f"find {state_dir} -maxdepth 1 -type f -delete",
            on_line,
        )
    current = profile.proxy_current_dir(provider)
    if current.exists():
        shutil.rmtree(current)
    current.mkdir(parents=True, exist_ok=True)
    on_line("[remote config removed; certificates/renewal timers, if any, are left untouched]")


def regenerate_config(profile: ServerProfile, provider: str, password: str | None, on_line: OnLine) -> str:
    """(Re)builds the client profile (Clash YAML / share link) for this
    proxy - for when it was lost, deleted, or just needs a fresh look at
    proxy-scripts/output/. Uses the locally cached client-info.json if
    present (no SSH needed at all); otherwise fetches it fresh from the
    server first, same as Deploy would, without re-running install.sh.

    Args:
        profile: Server the proxy belongs to.
        provider: Provider name of the proxy to regenerate a profile for.
        password: SSH password, or None if the server uses a key or a
            local cache already exists (unused in that case).
        on_line: Callback invoked with each line of progress/output.

    Returns:
        Path (as a string) to the local client-info.json used.
    """
    info_file = profile.proxy_current_dir(provider) / "client-info.json"
    if info_file.exists():
        on_line("[using locally cached client-info.json - no SSH needed]")
        _generate_client_profile(info_file, on_line)
        return str(info_file)

    on_line("[no local client-info.json found - fetching it from the server]")
    state_dir = _remote_state_dir(provider)
    with SSHSession(profile, password) as ssh:
        _sync_proxy_state(ssh, profile, provider, state_dir, on_line)
    return str(info_file)


def verify(profile: ServerProfile, provider: str, on_line: OnLine) -> bool:
    """Runs the provider's external verification (proxy-scripts/verify.sh)
    against the locally cached client-info.json - no SSH involved, this
    checks the proxy from the outside, the same way a real client would.

    Args:
        profile: Server the proxy belongs to.
        provider: Provider name of the proxy to verify.
        on_line: Callback invoked with each line of the script's output.

    Returns:
        True if verify.sh exited successfully; False if there's no local
        deployment to verify yet, or if verify.sh reported a failure.
    """
    info_file = profile.proxy_current_dir(provider) / "client-info.json"
    if not info_file.exists():
        on_line("[no deployment yet - run Deploy first]")
        return False
    result = subprocess.run(
        [str(PROXY_SCRIPTS_DIR / "verify.sh"), str(info_file)],
        capture_output=True,
        text=True,
    )
    for line in (result.stdout + result.stderr).splitlines():
        on_line(line)
    return result.returncode == 0
