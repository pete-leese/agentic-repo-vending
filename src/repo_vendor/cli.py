"""CLI entrypoint for Cloud Agent / local runs."""

from __future__ import annotations

import logging

import typer
from rich.console import Console

from repo_vendor.config import Settings, get_settings
from repo_vendor.workflow import rename_from_issue, vend_issue

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _with_dry_run(dry_run: bool) -> Settings:
    settings = get_settings()
    if not dry_run:
        return settings
    return Settings(**{**settings.model_dump(), "dry_run": True})


@app.command()
def vend(
    issue: str = typer.Option(..., "--issue", "-i", help="Jira issue key, e.g. KAN-12"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Log actions without mutating"),
) -> None:
    """Vend a GitHub repo from a Jira Repo Vend Request."""
    settings = _with_dry_run(dry_run)
    console.print(f"[bold]Vend[/bold] issue={issue} dry_run={settings.dry_run}")
    console.print(
        f"models: orchestrator={settings.orchestrator_model} eval={settings.eval_model}"
    )
    result = vend_issue(issue, settings)
    if result.success:
        console.print(f"[green]OK[/green] {result.message}")
        raise typer.Exit(0)
    console.print(f"[red]FAILED[/red] {result.message}")
    raise typer.Exit(1)


@app.command("rename")
def rename_cmd(
    issue: str = typer.Option(..., "--issue", "-i", help="Jira issue key"),
    current_name: str = typer.Option(..., "--current-name", help="Current GitHub repo name"),
    comment: str = typer.Option(..., "--comment", help="Comment text proposing the new name"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Re-eval and rename a vended repo from a Jira comment."""
    settings = _with_dry_run(dry_run)
    result = rename_from_issue(
        issue,
        current_name=current_name,
        comment_text=comment,
        settings=settings,
    )
    if result.success:
        console.print(f"[green]OK[/green] {result.message}")
        raise typer.Exit(0)
    console.print(f"[red]FAILED[/red] {result.message}")
    raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Print config readiness (does not print secret values)."""
    s = get_settings()
    checks = {
        "GITHUB_TOKEN": bool(s.github_token),
        "JIRA_EMAIL": bool(s.jira_email),
        "JIRA_API_TOKEN": bool(s.jira_api_token),
        "CURSOR_API_KEY": bool(s.cursor_api_key),
        "GITHUB_OWNER": s.github_owner,
        "ORCHESTRATOR_MODEL": s.orchestrator_model,
        "EVAL_MODEL": s.eval_model,
        "ALLOW_LLM_FALLBACK": s.allow_llm_fallback,
    }
    for k, v in checks.items():
        console.print(f"{k}: {v}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
