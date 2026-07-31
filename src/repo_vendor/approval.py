"""Keyword Approval matcher for the vend HITL gate."""

from __future__ import annotations

import re

from repo_vendor.config import Settings, get_settings


def build_approval_pattern(keywords: list[str]) -> re.Pattern[str]:
    """Compile Keyword Approval regex from config keywords.

    ``+1`` is matched as a substring (no lookbehind). Multi-word phrases allow
    flexible whitespace so ADF soft-breaks still match.
    """
    plus_one = False
    words: list[str] = []
    for raw in keywords:
        k = str(raw).strip()
        if not k:
            continue
        if k == "+1":
            plus_one = True
            continue
        words.append(re.escape(k).replace(r"\ ", r"\s+"))
    parts: list[str] = []
    if words:
        parts.append(rf"\b(?:{'|'.join(words)})\b")
    if plus_one:
        parts.append(r"\+1")
    if not parts:
        parts = [r"\b(?:approved|lgtm)\b"]
    return re.compile(rf"(?i)(?:{'|'.join(parts)})")


def is_approval_comment(text: str | None, settings: Settings | None = None) -> bool:
    if not text or not str(text).strip():
        return False
    settings = settings or get_settings()
    pattern = build_approval_pattern(list(settings.approval_keywords))
    return bool(pattern.search(str(text)))
