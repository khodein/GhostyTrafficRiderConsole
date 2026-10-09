"""Shared fixtures for the whole test suite.

Import style note: modules under ghosty_console/ do
`from ghosty_console.config import CONFIG_DIR` etc. in some places and
`from ghosty_console import config; config.CONFIG_DIR` in others - but
every *function* in config.py reads CONFIG_DIR/SERVERS_FILE as a module
global at call time, so monkeypatching the attributes on the `config`
module (not on whichever module happens to have imported a name from it)
is enough to redirect ALL of them, regardless of which module ends up
calling those functions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirects the local server registry (~/.config/ghosty-console) to a
    throwaway tmp_path for the duration of one test, so tests never read or
    write the real registry on your machine. Use this in every test that
    calls add_server/load_servers/ServerProfile.state_dir/deploy.* etc."""
    from ghosty_console import config

    config_dir = tmp_path / "ghosty-console"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "SERVERS_FILE", config_dir / "servers.yaml")
    return config


@pytest.fixture(autouse=True)
def _clean_generated_output():
    """generate-config.sh (real subprocess, not faked) always writes into
    proxy-scripts/output/ - the one thing tests can't redirect via
    isolated_config, since that path is baked into the provider scripts.
    Deletes whatever a test added there (files and the per-provider
    subdirectories created for them) so the repo's output/ directory doesn't
    accumulate test artifacts."""
    from ghosty_console.config import PROXY_SCRIPTS_DIR

    output_dir = PROXY_SCRIPTS_DIR / "output"

    def snapshot():
        paths = list(output_dir.rglob("*")) if output_dir.exists() else []
        return {p for p in paths if p.is_file()}, {p for p in paths if p.is_dir()}

    files_before, dirs_before = snapshot()
    yield
    files_after, dirs_after = snapshot()
    for path in files_after - files_before:
        path.unlink(missing_ok=True)
    for path in sorted(dirs_after - dirs_before, reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
