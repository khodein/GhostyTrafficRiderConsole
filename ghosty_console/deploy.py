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
    return PROXY_SCRIPTS_DIR / "providers" / provider


def _remote_scripts_dir(provider: str) -> str:
    return f"{REMOTE_SCRIPTS_ROOT}/{provider}"


def _remote_state_dir(provider: str) -> str:
    return f"{REMOTE_STATE_ROOT}/{provider}"


def deploy(
    profile: ServerProfile, provider: str, proxy_port: str, password: str | None, on_line: OnLine
) -> dict:
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
    which device originally ran Deploy."""
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
    its client config profile, and promotes the snapshot to current/."""
    snapshot = new_proxy_snapshot_dir(profile, provider)
    ssh.sftp_get(f"{state_dir}/client-info.json", snapshot / "client-info.json")
    _snapshot_remote_state(ssh, state_dir, snapshot)

    client_info = json.loads((snapshot / "client-info.json").read_text())
    _generate_client_profile(snapshot / "client-info.json", on_line)
    _promote_to_current(profile, provider, snapshot)
    return client_info


def _snapshot_remote_state(ssh: SSHSession, state_dir: str, snapshot: Path) -> None:
    """Copy every plain file directly under state_dir (skipping
    subdirectories like certs/ or build/) so rollback can push the same
    files back later, regardless of which provider they belong to."""
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
    current = profile.proxy_current_dir(provider)
    if current.exists():
        shutil.rmtree(current)
    shutil.copytree(snapshot, current)


def load_current_client_info(profile: ServerProfile, provider: str) -> dict | None:
    info_file = profile.proxy_current_dir(provider) / "client-info.json"
    if not info_file.exists():
        return None
    return json.loads(info_file.read_text())


def ping(profile: ServerProfile, provider: str | None = None) -> str:
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
    server first, same as Deploy would, without re-running install.sh."""
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
