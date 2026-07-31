#!/usr/bin/env python3
"""Build Cursor Automation prefillWorkflowData for repo-vend (webhook + Atlassian).

Prints JSON on stdout for open_automation.prefillWorkflowData.
Instructions are taken from docs/automation-setup.md (the paste fence).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP_DOC = ROOT / "docs" / "automation-setup.md"
CONFIG = ROOT / "repo-vend.yaml"


def _extract_instructions(md: str) -> str:
    # Prefer the fenced ```text block under Instructions
    blocks = re.findall(r"```text\n(.*?)```", md, flags=re.S)
    if not blocks:
        raise SystemExit("No ```text instruction fence found in docs/automation-setup.md")
    # First text fence in that doc is the Automation paste block
    return blocks[0].strip() + "\n"


def _owner_repo() -> tuple[str, str]:
    # Prefer gh; fall back to known default
    try:
        import subprocess

        out = subprocess.check_output(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=ROOT,
            text=True,
        ).strip()
        if "/" in out:
            owner, name = out.split("/", 1)
            return owner, name
    except Exception:  # noqa: BLE001
        pass
    return "pete-leese", "agentic-repo-vending"


def build_prefill(*, model: str = "composer-2.5", atlassian_server_name: str = "Atlassian") -> dict:
    instructions = _extract_instructions(SETUP_DOC.read_text(encoding="utf-8"))
    owner, repo = _owner_repo()
    return {
        "name": "repo-vend",
        "description": (
            "Jira webhook → propose/vend for agentic-repo-vending. "
            "Uses Atlassian tools for board I/O; CLI for evals + GitHub."
        ),
        "workflow": {
            "triggers": [{"webhook": {}}],
            "actions": [{"mcp": {"server": {"name": atlassian_server_name}}}],
            "prompts": [{"text": instructions}],
            "model": model,
            "memoryEnabled": True,
            "agentOptions": {"skipInstall": False},
            "gitConfig": {
                "repo": f"{owner}/{repo}",
                "branch": "main",
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="composer-2.5")
    parser.add_argument(
        "--atlassian-server-name",
        default="Atlassian",
        help="MCP serverName from Automations catalog (dashboard-eligible)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional path to write JSON (also always prints to stdout)",
    )
    args = parser.parse_args()
    data = build_prefill(model=args.model, atlassian_server_name=args.atlassian_server_name)
    text = json.dumps(data, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
