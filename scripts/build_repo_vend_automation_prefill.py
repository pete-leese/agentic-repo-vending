#!/usr/bin/env python3
"""Build Cursor Automation prefillWorkflowData for repo-vend (webhook + Atlassian).

Prints JSON on stdout for open_automation.prefillWorkflowData.
Instructions are taken from docs/automation-setup.md (the paste fence).
"""

from __future__ import annotations

import argparse
import json
import re
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


def build_prefill(
    *,
    model: str = "composer-2.5",
    atlassian_server_name: str = "Atlassian",
    extra_mcp_servers: list[str] | None = None,
) -> dict:
    instructions = _extract_instructions(SETUP_DOC.read_text(encoding="utf-8"))
    owner, repo = _owner_repo()
    mcp_actions: list[dict] = [{"mcp": {"server": {"name": atlassian_server_name}}}]
    seen = {atlassian_server_name}
    for name in extra_mcp_servers or _cloud_docs_mcp_names():
        if name and name not in seen:
            mcp_actions.append({"mcp": {"server": {"name": name}}})
            seen.add(name)
    return {
        "name": "repo-vend",
        "description": (
            "Jira webhook → propose/vend for agentic-repo-vending. "
            "Uses Atlassian tools for board I/O; optional cloud-docs MCP; CLI for evals + GitHub."
        ),
        "workflow": {
            "triggers": [{"webhook": {}}],
            "actions": mcp_actions,
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


def _cloud_docs_mcp_names() -> list[str]:
    """Read enabled provider mcp_server names from repo-vend.yaml."""
    try:
        from repo_vendor.cloud_docs import cloud_docs_mcp_server_names

        return cloud_docs_mcp_server_names()
    except Exception:  # noqa: BLE001
        pass
    # Script may run without the package on PYTHONPATH — parse YAML directly.
    try:
        import yaml
    except ImportError:
        return []
    if not CONFIG.is_file():
        return []
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    section = data.get("cloud_docs") if isinstance(data, dict) else None
    if not isinstance(section, dict) or section.get("enabled") is False:
        return []
    providers = section.get("providers")
    if not isinstance(providers, dict):
        return []
    names: list[str] = []
    for entry in providers.values():
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        name = entry.get("mcp_server")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="composer-2.5")
    parser.add_argument(
        "--atlassian-server-name",
        default="Atlassian",
        help="MCP serverName from Automations catalog (dashboard-eligible)",
    )
    parser.add_argument(
        "--mcp-server",
        action="append",
        default=[],
        help="Extra MCP serverName to prefill (repeatable). "
        "Defaults to enabled cloud_docs.providers from repo-vend.yaml.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional path to write JSON (also always prints to stdout)",
    )
    args = parser.parse_args()
    extra = args.mcp_server or None
    data = build_prefill(
        model=args.model,
        atlassian_server_name=args.atlassian_server_name,
        extra_mcp_servers=extra,
    )
    text = json.dumps(data, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
