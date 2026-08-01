"""Contract tests for Cursor project hooks (JSON decision on stdout)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".cursor" / "hooks"


def _run_hook(script: str, payload: dict, *args: str) -> dict:
    proc = subprocess.run(
        ["bash", str(HOOKS / script), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


def test_security_hook_allows_normal_write():
    out = _run_hook(
        "security_hook.sh",
        {"file_path": "src/repo_vendor/naming.py"},
        "--tool-edit",
    )
    assert out["permission"] == "allow"


def test_security_hook_denies_dotenv_write():
    out = _run_hook(
        "security_hook.sh",
        {"file_path": str(ROOT / ".env")},
        "--tool-edit",
    )
    assert out["permission"] == "deny"


def test_security_hook_denies_force_push():
    out = _run_hook(
        "security_hook.sh",
        {"command": "git push --force origin main"},
    )
    assert out["permission"] == "deny"


def test_security_hook_allows_safe_shell():
    out = _run_hook(
        "security_hook.sh",
        {"command": "git status"},
    )
    assert out["permission"] == "allow"


def _hook_script_path(command: str) -> Path:
    """Extract `.cursor/hooks/*.sh` path from a hooks.json command string."""
    for token in command.split():
        cleaned = token[2:] if token.startswith("./") else token
        if cleaned.endswith(".sh") and "hooks" in cleaned:
            return ROOT / cleaned
    raise AssertionError(f"no hook script in command: {command}")


def test_hooks_json_lists_expected_events():
    data = json.loads((ROOT / ".cursor" / "hooks.json").read_text())
    assert data["version"] == 1
    assert "beforeShellExecution" in data["hooks"]
    assert "preToolUse" in data["hooks"]
    for section in ("beforeShellExecution", "preToolUse"):
        for entry in data["hooks"][section]:
            path = _hook_script_path(entry["command"])
            assert path.is_file(), entry["command"]
            assert os.access(path, os.X_OK), f"not executable: {path}"
