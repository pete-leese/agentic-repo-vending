"""Load machine-enforced naming rules from ``rules/deterministic.yaml``.

Edit the YAML to change patterns / platforms / stopwords / aliases.
This module only parses, expands placeholders, and compiles regexes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from repo_vendor.models import Platform
from repo_vendor.prompts import find_repo_root


@dataclass(frozen=True)
class DeterministicRules:
    """Compiled gate rules sourced from ``rules/deterministic.yaml``."""

    platforms: tuple[str, ...]
    kebab: re.Pattern[str]
    terraform_module: re.Pattern[str]
    terraform_root: re.Pattern[str]
    python: re.Pattern[str]
    generic: re.Pattern[str]
    displays: dict[str, str]
    purpose_stopwords: frozenset[str]
    reserved_prefixes: tuple[str, ...]
    service_aliases: dict[str, Platform]
    alias_pattern: re.Pattern[str]


def _rules_path() -> Path:
    candidates: list[Path] = []
    try:
        candidates.append(find_repo_root() / "rules" / "deterministic.yaml")
    except FileNotFoundError:
        pass
    candidates.append(Path.cwd() / "rules" / "deterministic.yaml")
    bundled = Path(__file__).resolve().parent / "_bundled" / "rules" / "deterministic.yaml"
    candidates.append(bundled)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Could not find rules/deterministic.yaml (repo checkout or package bundle)."
    )


def _expand(pattern: str, *, platforms: list[str], reserved_prefixes: list[str]) -> str:
    plat = "|".join(re.escape(p) for p in platforms)
    reserved = "|".join(re.escape(p) for p in reserved_prefixes)
    return pattern.replace("{platforms}", plat).replace("{reserved_prefixes}", reserved)


def _require_pattern(data: dict[str, Any], key: str) -> dict[str, Any]:
    patterns = data.get("patterns")
    if not isinstance(patterns, dict) or key not in patterns:
        raise ValueError(f"rules/deterministic.yaml missing patterns.{key}")
    entry = patterns[key]
    if not isinstance(entry, dict) or "regex" not in entry:
        raise ValueError(f"rules/deterministic.yaml patterns.{key} needs regex")
    return entry


def _token_str(value: Any) -> str:
    """Normalize YAML scalars (quote on/off/yes/no — PyYAML may yield bools)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).lower()


def _compile_rules(data: dict[str, Any]) -> DeterministicRules:
    platforms_raw = data.get("platforms")
    if not isinstance(platforms_raw, list) or not platforms_raw:
        raise ValueError("rules/deterministic.yaml needs a non-empty platforms list")
    platforms = [_token_str(p) for p in platforms_raw]
    for p in platforms:
        Platform(p)  # validate against enum

    reserved_raw = data.get("reserved_prefixes") or ["terraform-", "python-"]
    if not isinstance(reserved_raw, list) or not reserved_raw:
        raise ValueError("rules/deterministic.yaml needs reserved_prefixes")
    reserved = [str(x) for x in reserved_raw]

    kebab_block = data.get("kebab") or {}
    if not isinstance(kebab_block, dict) or "regex" not in kebab_block:
        raise ValueError("rules/deterministic.yaml needs kebab.regex")
    kebab = re.compile(str(kebab_block["regex"]))

    displays: dict[str, str] = {}
    compiled: dict[str, re.Pattern[str]] = {}
    for key in ("terraform_module", "terraform_root", "python", "generic"):
        entry = _require_pattern(data, key)
        regex = _expand(str(entry["regex"]), platforms=platforms, reserved_prefixes=reserved)
        compiled[key] = re.compile(regex)
        displays[key] = str(entry.get("display") or key)

    stop_raw = data.get("purpose_stopwords") or []
    if not isinstance(stop_raw, list):
        raise ValueError("rules/deterministic.yaml purpose_stopwords must be a list")
    # Unquoted YAML 1.1 turns on/yes/true → True and off/no/false → False.
    _bool_words = {True: ("on", "yes", "true"), False: ("off", "no", "false")}
    stop_tokens: set[str] = set()
    for item in stop_raw:
        if isinstance(item, bool):
            stop_tokens.update(_bool_words[item])
        else:
            stop_tokens.add(str(item).lower())
    stopwords = frozenset(stop_tokens)

    aliases_raw = data.get("platform_service_aliases") or {}
    if not isinstance(aliases_raw, dict):
        raise ValueError("rules/deterministic.yaml platform_service_aliases must be a mapping")
    service_aliases: dict[str, Platform] = {}
    for platform_key, services in aliases_raw.items():
        platform = Platform(str(platform_key).lower())
        if not isinstance(services, list):
            raise ValueError(
                f"rules/deterministic.yaml platform_service_aliases.{platform_key} must be a list"
            )
        for service in services:
            token = str(service).lower().replace(" ", "-")
            service_aliases[token] = platform
            # Also match spaced form in ticket text ("transit gateway" ↔ transit-gateway).
            spaced = token.replace("-", " ")
            if spaced != token:
                service_aliases[spaced] = platform

    if service_aliases:
        alias_pattern = re.compile(
            r"\b("
            + "|".join(re.escape(k) for k in sorted(service_aliases, key=len, reverse=True))
            + r")\b",
            re.I,
        )
    else:
        alias_pattern = re.compile(r"(?!x)x")  # never matches

    return DeterministicRules(
        platforms=tuple(platforms),
        kebab=kebab,
        terraform_module=compiled["terraform_module"],
        terraform_root=compiled["terraform_root"],
        python=compiled["python"],
        generic=compiled["generic"],
        displays=displays,
        purpose_stopwords=stopwords,
        reserved_prefixes=tuple(reserved),
        service_aliases=service_aliases,
        alias_pattern=alias_pattern,
    )


@lru_cache
def load_deterministic_rules() -> DeterministicRules:
    path = _rules_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    return _compile_rules(data)


def clear_deterministic_rules_cache() -> None:
    """Test helper — reload after swapping YAML fixtures."""
    load_deterministic_rules.cache_clear()


def display_for(pattern_key: str) -> str:
    return load_deterministic_rules().displays.get(pattern_key, pattern_key)


class _LazyPattern:
    """Module-level ``TF_MODULE.fullmatch(...)`` compatibility."""

    def __init__(self, attr: str) -> None:
        self._attr = attr

    def _pat(self) -> re.Pattern[str]:
        return getattr(load_deterministic_rules(), self._attr)

    def fullmatch(self, string: str, pos: int = 0, endpos: int | None = None):  # noqa: ANN201
        if endpos is None:
            return self._pat().fullmatch(string, pos)
        return self._pat().fullmatch(string, pos, endpos)

    def match(self, string: str, pos: int = 0, endpos: int | None = None):  # noqa: ANN201
        if endpos is None:
            return self._pat().match(string, pos)
        return self._pat().match(string, pos, endpos)

    def search(self, string: str, pos: int = 0, endpos: int | None = None):  # noqa: ANN201
        if endpos is None:
            return self._pat().search(string, pos)
        return self._pat().search(string, pos, endpos)

    def __repr__(self) -> str:
        return f"<LazyPattern {self._attr} {self._pat().pattern!r}>"
