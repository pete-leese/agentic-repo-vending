"""CLI entrypoint for Cloud Agent / local runs.

Jira board updates are performed by the Cursor Automation using Atlassian tools.
This CLI runs propose (evals + Spec PR) and vend (merge Spec + create-from-template).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import IssueSnapshot
from repo_vendor.observability import (
    configure_metrics_from_env,
    flush_metrics,
    otlp_endpoint_configured,
    shutdown_metrics,
)
from repo_vendor.workflow import propose_issue, vend_issue

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console(stderr=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@app.callback()
def _cli_bootstrap() -> None:
    """Configure metrics once per process (OTLP → Grafana Cloud when OTEL_* set)."""
    configure_metrics_from_env()


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
        print(json.dumps(payload, indent=2))
    else:
        console.print(
            f"[bold]phase={result.phase} outcome={result.outcome}[/bold] success={result.success}"
        )
        console.print(result.message)
        console.print("Jira plan (apply with Atlassian tools):")
        console.print(json.dumps(payload["jira"], indent=2))


@app.command()
def propose(
    issue_json: str | None = typer.Option(
        None,
        "--issue-json",
        help="IssueSnapshot JSON (fields + optional additional_context)",
    ),
    issue_file: Path | None = typer.Option(
        None,
        "--issue-file",
        exists=True,
        dir_okay=False,
        help="Path to IssueSnapshot JSON file",
    ),
    cursor_agent_id: str | None = typer.Option(
        None,
        "--cursor-agent-id",
        help="Cloud Agent id (bc-…) to hyperlink in the Jira comment",
    ),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Print full result JSON on stdout"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run evals and open a Spec Request PR (no create-from-template)."""
    settings = _with_dry_run(dry_run)
    issue = _load_issue(issue_json, issue_file)
    console.print(f"[bold]Propose[/bold] issue={issue.key} dry_run={settings.dry_run}")
    console.print(f"models: orchestrator={settings.orchestrator_model} eval={settings.eval_model}")
    try:
        result = propose_issue(issue, settings, cursor_agent_id=cursor_agent_id)
        _emit(result, as_json=as_json)
        code = 0 if result.success else 1
    finally:
        flush_metrics()
        shutdown_metrics()
    raise typer.Exit(code)


@app.command()
def vend(
    issue_json: str | None = typer.Option(
        None,
        "--issue-json",
        help="IssueSnapshot JSON (fields + optional additional_context)",
    ),
    issue_file: Path | None = typer.Option(
        None,
        "--issue-file",
        exists=True,
        dir_okay=False,
        help="Path to IssueSnapshot JSON file",
    ),
    approval_comment: str | None = typer.Option(
        None,
        "--approval-comment",
        help="Comment body that must match Keyword Approval (approved|lgtm|...)",
    ),
    cursor_agent_id: str | None = typer.Option(
        None,
        "--cursor-agent-id",
        help="Cloud Agent id (bc-…) to hyperlink in the Jira comment",
    ),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Print full result JSON on stdout"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Merge Spec Request if needed and create GitHub repo from frozen YAML."""
    settings = _with_dry_run(dry_run)
    issue = _load_issue(issue_json, issue_file)
    console.print(f"[bold]Vend[/bold] issue={issue.key} dry_run={settings.dry_run}")
    try:
        result = vend_issue(
            issue,
            approval_comment=approval_comment,
            settings=settings,
            cursor_agent_id=cursor_agent_id,
        )
        _emit(result, as_json=as_json)
        code = 0 if result.success else 1
    finally:
        flush_metrics()
        shutdown_metrics()
    raise typer.Exit(code)


@app.command()
def doctor() -> None:
    """Print config readiness (does not print secret values)."""
    from repo_vendor.project_config import project_config_path

    s = get_settings()
    checks = {
        "GITHUB_TOKEN": bool(s.github_token),
        "CURSOR_API_KEY": bool(s.cursor_api_key),
        "GITHUB_OWNER": s.github_owner,
        "CONTROL_PLANE_REPO": s.control_plane_repo,
        "JIRA_BOARD_URL": s.jira_board_url,
        "TEMPLATES": (
            f"tf={s.template_terraform} py={s.template_python} generic={s.template_generic}"
        ),
        "DEFAULT_PROJECT_TYPE": s.default_project_type,
        "APPROVAL_KEYWORDS": ", ".join(s.approval_keywords),
        "ORCHESTRATOR_MODEL": s.orchestrator_model,
        "EVAL_MODEL": s.eval_model,
        "ALLOW_LLM_FALLBACK": s.allow_llm_fallback,
        "OTEL_EXPORTER_OTLP_ENDPOINT": otlp_endpoint_configured(),
        "OTEL_SERVICE_NAME": bool(os.environ.get("OTEL_SERVICE_NAME", "").strip()),
        "repo-vend.yaml": str(project_config_path() or "(not found)"),
        "note": "Jira I/O via Atlassian tools; HITL = Keyword Approval after propose",
    }
    for k, v in checks.items():
        console.print(f"{k}: {v}")


@app.command("metrics-smoke")
def metrics_smoke() -> None:
    """Emit test metrics and flush to OTLP (diagnose Grafana Cloud wiring)."""
    from repo_vendor.observability import MetricEvent, _service_name, get_metrics_sink

    if not otlp_endpoint_configured():
        console.print("[red]OTEL_EXPORTER_OTLP_ENDPOINT is not set[/red]")
        raise typer.Exit(1)
    sink = get_metrics_sink()
    svc = _service_name()
    sink.emit(
        MetricEvent(
            name="span.smoke",
            value=1.0,
            attributes={"status": "ok", "issue_key": "SMOKE"},
        )
    )
    sink.emit(
        MetricEvent(
            name="eval.result",
            value=1.0,
            attributes={"passed": True, "stage": "smoke", "issue_key": "SMOKE"},
        )
    )
    sink.emit(
        MetricEvent(
            name="vend.result",
            value=1.0,
            attributes={
                "success": True,
                "phase": "propose",
                "issue_key": "SMOKE",
            },
        )
    )
    sink.record_tokens(model="smoke-model", input_tokens=42, output_tokens=7)
    try:
        ok = flush_metrics(timeout_millis=15_000)
        console.print(f"flush_ok={ok} service_name={svc}")
        console.print(
            'Grafana Explore (Prometheus datasource for this stack): {__name__=~"repo_vend.*"}'
        )
        console.print(
            "If panels stay empty: re-import docs/grafana/repo-vend-dashboard.json, "
            "pick the Grafana Cloud Prometheus/Mimir datasource (not Application "
            "Observability), set time range to last 1h, wait ~1–2 min after flush."
        )
        console.print(
            "If flush_ok=True but Explore is empty, check agent logs for OTLP 401 "
            "and strip quotes from OTEL_EXPORTER_OTLP_HEADERS."
        )
        raise typer.Exit(0 if ok else 1)
    finally:
        shutdown_metrics()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
