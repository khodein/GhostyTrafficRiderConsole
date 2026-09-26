"""Shell script sanity: tests/test_shell_syntax.py
Covers: every *.sh under proxy-scripts/, syntax-checked with `bash -n`
(catches typos/quoting bugs immediately, without needing a VPS).

New provider scripts are picked up automatically - nothing to add here.
"""
import subprocess

import pytest

from ghosty_console.config import PROXY_SCRIPTS_DIR


def _all_shell_scripts() -> list:
    return sorted(PROXY_SCRIPTS_DIR.rglob("*.sh"))


@pytest.mark.parametrize(
    "script", _all_shell_scripts(), ids=lambda p: str(p.relative_to(PROXY_SCRIPTS_DIR))
)
def test_shell_script_syntax(script):
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
