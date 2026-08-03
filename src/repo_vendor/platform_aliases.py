"""Map cloud-specific service names to Platform (aws|gcp|azure).

Aliases are defined in ``rules/deterministic.yaml`` (``platform_service_aliases``).
Documented for LLM extract / judge via ``rules/naming.md``.
"""

from __future__ import annotations

import re

from repo_vendor.deterministic_rules import load_deterministic_rules
from repo_vendor.models import Platform


def _aliases() -> dict[str, Platform]:
    return load_deterministic_rules().service_aliases


# Back-compat for imports / introspection (live view of YAML-backed map).
def __getattr__(name: str):  # noqa: ANN201
    if name == "PLATFORM_SERVICE_ALIASES":
        return _aliases()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def infer_platform_from_text(blob: str) -> Platform | None:
    """Return platform implied by an explicit cloud name or a known service alias."""
    rules = load_deterministic_rules()
    lower = blob.lower()
    for p in rules.platforms:
        if f"platform-{p}" in lower or re.search(rf"\b{re.escape(p)}\b", lower):
            return Platform(p)
    m = rules.alias_pattern.search(lower)
    if not m:
        return None
    return rules.service_aliases[m.group(1).lower().replace(" ", "-")]
