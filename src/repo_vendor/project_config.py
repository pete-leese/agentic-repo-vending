"""Load repo-vend.yaml project config (board URL, approval keywords, templates)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from repo_vendor.prompts import find_repo_root


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


@lru_cache
def load_project_config() -> dict[str, Any]:
    """Load repo-vend.yaml from the control-plane checkout (or bundled copy)."""
    candidates: list[Path] = []
    try:
        root = find_repo_root()
        candidates.append(root / "repo-vend.yaml")
    except FileNotFoundError:
        pass
    candidates.append(Path.cwd() / "repo-vend.yaml")
    bundled = Path(__file__).resolve().parent / "_bundled" / "repo-vend.yaml"
    candidates.append(bundled)
    for path in candidates:
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError(f"{path} must be a YAML mapping")
            return data
    return {}


def project_config_path() -> Path | None:
    try:
        path = find_repo_root() / "repo-vend.yaml"
        return path if path.is_file() else None
    except FileNotFoundError:
        cwd = Path.cwd() / "repo-vend.yaml"
        return cwd if cwd.is_file() else None


def cfg_str(data: dict[str, Any], *keys: str, default: str = "") -> str:
    value = _deep_get(data, *keys, default=default)
    return str(value) if value is not None else default


def cfg_keywords(data: dict[str, Any]) -> list[str]:
    raw = _deep_get(data, "jira", "approval", "keywords", default=None)
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw]
    return ["approved", "lgtm", "looks good", "ship it", "+1"]
