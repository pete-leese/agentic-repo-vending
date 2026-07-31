"""CLI entrypoint for Cloud Agent / local runs.

Jira board updates are performed by the Cursor Automation using Atlassian tools.
This CLI only runs evals + GitHub and prints a JSON plan for Jira side-effects.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import IssueSnapshot
from repo_vendor.workflow import rename_from_issue, vend_issue

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console(stderr=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _with_dry_run(dry_run: bool) -> Settings:
    settings = get_settings()
    if not dry_run:
        return settings
    return Settings(**{**settings.model_dump(), "dry_run": True})


def _load_issue(issue_json: str | None, issue_file: Path | None) -> IssueSnapshot:
    raw: str
    if issue_file is not None:
        raw = issue_file.read_text(encoding="utf-8")
    elif issue_json:
        raw = issue_json
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        raise typer.BadParameter(
            "Provide --issue-json, --issue-file, or pipe IssueSnapshot JSON on stdin"
        )
    return IssueSnapshot.model_validate_json(raw)


def _emit(result, *, as_json: bool) -> None:
    payload = result.model_dump()
    if as_json:
        # Machine-readable on stdout for the Automation to parse
        print(json.dumps(payload, indent=2))
    else:
        console.print(f"[bold]outcome={result.outcome}[/bold] success={result.success}")
        console.print(result.message)
        console.print("Jira plan (apply with Atlassian tools):")
        console.print(json.dumps(payload["jira"], indent=2))


@app.command()
def vend(
    issue_json: str | None = typer.Option(
        None,
        "--issue-json",
        help="IssueSnapshot JSON (key, summary, description, status, labels)",
    ),
    issue_file: Path | None = typer.Option(
        None,
        "--issue-file",
        exists=True,
        dir_okay=False,
        help="Path to IssueSnapshot JSON file",
    ),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Print full result JSON on stdout"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Vend a GitHub repo from an issue snapshot (Jira I/O via Atlassian Automation tools)."""
    settings = _with_dry_run(dry_run)
    issue = _load_issue(issue_json, issue_file)
    console.print(f"[bold]Vend[/bold] issue={issue.key} dry_run={settings.dry_run}")
    console.print(
        f"models: orchestrator={settings.orchestrator_model} eval={settings.eval_model}"
    )
    result = vend_issue(issue, settings)
    _emit(result, as_json=as_json)
    raise typer.Exit(0 if result.success else 1)


@app.command("rename")
def rename_cmd(
    current_name: str = typer.Option(..., "--current-name", help="Current GitHub repo name"),
    comment: str = typer.Option(..., "--comment", help="Comment text proposing the new name"),
    issue_json: str | None = typer.Option(None, "--issue-json"),
    issue_file: Path | None = typer.Option(None, "--issue-file", exists=True, dir_okay=False),
    as_json: bool = typer.Option(True, "--json/--no-json"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Re-eval and rename; apply result.jira with Atlassian tools."""
    settings = _with_dry_run(dry_run)
    issue = _load_issue(issue_json, issue_file)
    result = rename_from_issue(
        issue,
        current_name=current_name,
        comment_text=comment,
        settings=settings,
    )
    _emit(result, as_json=as_json)
    raise typer.Exit(0 if result.success else 1)


@app.command()
def doctor() -> None:
    """Print config readiness (does not print secret values)."""
    s = get_settings()
    checks = {
        "GITHUB_TOKEN": bool(s.github_token),
        "CURSOR_API_KEY": bool(s.cursor_api_key),
        "GITHUB_OWNER": s.github_owner,
        "ORCHESTRATOR_MODEL": s.orchestrator_model,
        "EVAL_MODEL": s.eval_model,
        "ALLOW_LLM_FALLBACK": s.allow_llm_fallback,
        "note": "Jira board I/O uses Atlassian Automation tools (not JIRA_* env in CLI)",
    }
    for k, v in checks.items():
        console.print(f"{k}: {v}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
