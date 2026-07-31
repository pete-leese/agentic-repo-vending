"""Spec Request YAML helpers (requests/<ISSUE-KEY>.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml

from repo_vendor.models import SpecRequest
from repo_vendor.prompts import find_repo_root


def request_rel_path(issue_key: str) -> str:
    return f"requests/{issue_key}.yaml"


def request_local_path(issue_key: str, root: Path | None = None) -> Path:
    base = root or find_repo_root()
    return base / request_rel_path(issue_key)


def spec_to_yaml(spec: SpecRequest) -> str:
    data = spec.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def spec_from_yaml(text: str) -> SpecRequest:
    data = yaml.safe_load(text) or {}
    return SpecRequest.model_validate(data)


def write_spec_local(spec: SpecRequest, root: Path | None = None) -> Path:
    path = request_local_path(spec.issue_key, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spec_to_yaml(spec), encoding="utf-8")
    return path
