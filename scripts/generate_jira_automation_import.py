#!/usr/bin/env python3
"""Generate an importable Jira Automation JSON for propose / re-propose / vend.

Usage:
  python scripts/generate_jira_automation_import.py --webhook-url URL [--out PATH]

Reads repo-vend.yaml for site base_url, New Request status, and approval keywords.
Starts from docs/jira/automation-rules-two-phase.json (structure + project ARIs).

Rules in the template:
  - repo-vend-propose          — issue created → propose
  - repo-vend-propose-on-edit  — summary/description edit → propose
  - repo-vend-propose-on-label — helper label add (platform-|tf-|type-*) → propose
  - repo-vend-approve          — Keyword Approval comment → vend
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs" / "jira" / "automation-rules-two-phase.json"
DEFAULT_OUT = ROOT / "docs" / "jira" / "automation-rules-import.json"
CONFIG_PATH = ROOT / "repo-vend.yaml"
AUTH_PLACEHOLDER = "Bearer REPLACE_WITH_CURSOR_WEBHOOK_API_KEY"
WEBHOOK_URL_RE = re.compile(
    r"^https://api2\.cursor\.sh/automations/webhook/[0-9a-fA-F-]{20,}$"
)


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _approval_regex(keywords: list[str]) -> str:
    """Regex for Jira Automation REGEX_CONTAINS on {{comment.body.text}}.

    Avoid lookbehind — Atlassian’s regex engine often rejects ``(?<!…)`` and then
    the whole condition silently fails (audit: No actions performed), especially
    on threaded replies where ADF markup already makes matching fragile.
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
        # Allow flexible whitespace inside multi-word phrases (ADF / soft breaks)
        words.append(re.escape(k).replace(r"\ ", r"\s+"))
    parts: list[str] = []
    if words:
        parts.append(rf"\b(?:{'|'.join(words)})\b")
    if plus_one:
        parts.append(r"\+1")
    if not parts:
        parts = [r"\b(?:approved|lgtm)\b"]
    return rf"(?i)(?:{'|'.join(parts)})"


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _rewire_ids(obj: object, id_map: dict[str, str]) -> object:
    """Replace UUID-looking string ids with freshly generated ones (stable within file)."""

    def map_id(value: str) -> str:
        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value,
        ):
            if value not in id_map:
                id_map[value] = _new_uuid()
            return id_map[value]
        return value

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in {"id", "idUuid", "conditionParentId", "parentId"} and isinstance(v, str):
                out[k] = map_id(v) if v else v
            else:
                out[k] = _rewire_ids(v, id_map)
        return out
    if isinstance(obj, list):
        return [_rewire_ids(x, id_map) for x in obj]
    return obj


def _set_webhook_urls(obj: object, webhook_url: str) -> None:
    if isinstance(obj, dict):
        if obj.get("type") == "jira.issue.outgoing.webhook" and isinstance(obj.get("value"), dict):
            obj["value"]["url"] = webhook_url
            headers = obj["value"].get("headers") or []
            for h in headers:
                if isinstance(h, dict) and h.get("name") == "Authorization":
                    h["value"] = AUTH_PLACEHOLDER
                    h["headerSecure"] = True
        for v in obj.values():
            _set_webhook_urls(v, webhook_url)
    elif isinstance(obj, list):
        for item in obj:
            _set_webhook_urls(item, webhook_url)


def _patch_from_config(data: dict, cfg: dict) -> None:
    jira = cfg.get("jira") or {}
    statuses = jira.get("statuses") or {}
    labels = jira.get("labels") or {}
    keywords = (jira.get("approval") or {}).get("keywords") or [
        "approved",
        "lgtm",
        "looks good",
        "ship it",
        "+1",
    ]
    new_request = statuses.get("new_request") or "New Request"
    vended = labels.get("vended") or "repo-vended"
    regex = _approval_regex([str(k) for k in keywords])

    for rule in data.get("rules") or []:
        trigger = rule.get("trigger") or {}
        for cond in trigger.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            value = cond.get("value") or {}
            # Status EQUALS New Request
            if (
                cond.get("type") == "jira.issue.condition"
                and value.get("selectedFieldType") == "status"
                and value.get("comparison") == "EQUALS"
            ):
                cv = value.get("compareValue") or {}
                cv["value"] = new_request
                value["compareValue"] = cv
            # Labels CONTAINS_NONE repo-vended
            if (
                cond.get("type") == "jira.issue.condition"
                and value.get("selectedFieldType") == "labels"
                and value.get("comparison") == "CONTAINS_NONE"
            ):
                cv = value.get("compareValue") or {}
                cv["value"] = json.dumps([vended])
                value["compareValue"] = cv
            # Keyword regex (approve rule only — do not overwrite label-retrigger regex)
            if (
                cond.get("type") == "jira.comparator.condition"
                and value.get("first")
                in {
                    "{{comment.body}}",
                    "{{comment.body.text}}",
                    "{{issue.comments.last.body}}",
                    "{{issue.comments.last.body.text}}",
                }
                and value.get("operator")
                in {"REGEX_MATCHES", "REGEX_CONTAINS", "CONTAINS_REGEX"}
            ):
                value["first"] = "{{comment.body.text}}"
                value["second"] = regex
                value["operator"] = "REGEX_CONTAINS"


def generate(webhook_url: str, *, template: Path, out: Path) -> dict:
    if not WEBHOOK_URL_RE.match(webhook_url.strip()):
        raise SystemExit(
            "Webhook URL must look like: "
            "https://api2.cursor.sh/automations/webhook/<automation-id>\n"
            f"Got: {webhook_url!r}"
        )
    webhook_url = webhook_url.strip().rstrip("/")
    raw = json.loads(template.read_text(encoding="utf-8"))
    cfg = _load_config()
    data = _rewire_ids(raw, {})
    assert isinstance(data, dict)
    _set_webhook_urls(data, webhook_url)
    _patch_from_config(data, cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "out": str(out),
        "webhook_url": webhook_url,
        "base_url": (cfg.get("jira") or {}).get("base_url")
        or "https://YOUR.atlassian.net",
        "board_url": (cfg.get("jira") or {}).get("board_url") or "",
        "automation_settings_url": (
            f"{((cfg.get('jira') or {}).get('base_url') or 'https://YOUR.atlassian.net').rstrip('/')}"
            "/jira/settings/automation"
        ),
        "keywords": (cfg.get("jira") or {}).get("approval", {}).get("keywords")
        or ["approved", "lgtm", "looks good", "ship it", "+1"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webhook-url", required=True, help="Cursor Automation webhook URL")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.template.is_file():
        raise SystemExit(f"Template not found: {args.template}")
    meta = generate(args.webhook_url, template=args.template, out=args.out)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
