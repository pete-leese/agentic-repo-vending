"""Resolve Cursor Cloud Agent run id + dashboard URL for Jira comments."""

from __future__ import annotations

import os
import re

_BC_ID = re.compile(r"^bc-[0-9a-fA-F-]{8,}$")
_ENV_KEYS = (
    "CURSOR_CLOUD_AGENT_ID",
    "CURSOR_AGENT_ID",
    "CLOUD_AGENT_ID",
    "CURSOR_AGENT_BC_ID",
)


def normalize_cursor_agent_id(raw: str | None) -> str | None:
    if not raw:
        return None
    value = str(raw).strip()
    if not value:
        return None
    # Allow bare UUID → bc-<uuid>
    if re.fullmatch(r"[0-9a-fA-F-]{36}", value):
        value = f"bc-{value}"
    if not _BC_ID.match(value):
        return None
    return value


def cursor_agent_url(agent_id: str) -> str:
    return f"https://cursor.com/agents/{agent_id}"


def resolve_cursor_agent(
    *,
    agent_id: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(agent_id, url)`` from an explicit id or known env vars."""
    candidates: list[str] = []
    if agent_id:
        candidates.append(agent_id)
    source = env if env is not None else os.environ
    for key in _ENV_KEYS:
        val = source.get(key)
        if val:
            candidates.append(val)
    for raw in candidates:
        normalized = normalize_cursor_agent_id(raw)
        if normalized:
            return normalized, cursor_agent_url(normalized)
    return None, None


def format_cursor_agent_line(
    *,
    agent_id: str | None = None,
    agent_url: str | None = None,
) -> str | None:
    if not agent_id:
        return None
    url = agent_url or cursor_agent_url(agent_id)
    return f"- **Cursor agent:** [`{agent_id}`]({url})"
