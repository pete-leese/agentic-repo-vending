"""Load eval prompts from /evals/*.json and rules from /rules/*.md."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start (or this file) until evals/ + rules/ exist.

    Also accepts the wheel-bundled layout under ``repo_vendor/_bundled/``.
    """
    here = start or Path(__file__).resolve()
    candidates = [here, *here.parents, Path.cwd()]
    bundled = Path(__file__).resolve().parent / "_bundled"
    if bundled.is_dir():
        candidates.append(bundled)
    for candidate in candidates:
        if (candidate / "evals").is_dir() and (candidate / "rules").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not find evals/ and rules/ (repo checkout or package bundle). "
        "Run from the agentic-repo-vending checkout."
    )


@lru_cache
def load_eval(eval_id: str) -> dict[str, Any]:
    """Load evals/<eval_id>.json (e.g. extract-intent, judge-naming)."""
    path = find_repo_root() / "evals" / f"{eval_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Eval definition not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Eval {eval_id} must be a JSON object")
    return data


def load_rules(rel_path: str = "rules/naming.md") -> str:
    path = find_repo_root() / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"Rules file not found: {path}")
    return path.read_text(encoding="utf-8")


def format_user_prompt(eval_id: str, **kwargs: Any) -> tuple[str, str]:
    """Return (system, user) prompts for an eval, injecting rules when referenced."""
    spec = load_eval(eval_id)
    system = str(spec["system"])
    template = str(spec["user_template"])
    rules_ref = spec.get("rules_ref")
    if rules_ref and "{rules}" in template:
        kwargs = {**kwargs, "rules": load_rules(str(rules_ref))}
    return system, template.format(**kwargs)
