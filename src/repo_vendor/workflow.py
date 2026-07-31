"""Vend/rename orchestration: evals + GitHub only. Jira is applied by Atlassian Automation tools."""

from __future__ import annotations

import logging
import re

from repo_vendor.config import Settings, get_settings
from repo_vendor.github_client import GitHubClient
from repo_vendor.harness import eval_with_harness, extract_intent_with_harness, get_harness
from repo_vendor.models import IssueSnapshot, JiraUpdatePlan, VendResult
from repo_vendor.naming import to_kebab, validate_name_and_template
from repo_vendor.observability import record_eval, record_vend, span

logger = logging.getLogger(__name__)


def _outcome_labels(settings: Settings, outcome: str) -> tuple[list[str], list[str]]:
    """Return (labels_add, labels_remove) for success|warning|error."""
    success = settings.jira_label_success
    warning = settings.jira_label_warning
    error = settings.jira_label_error
    all_outcomes = [success, warning, error]
    chosen = {"success": success, "warning": warning, "error": error}[outcome]
    return [chosen], [lbl for lbl in all_outcomes if lbl != chosen]


def _failure_markdown(errors: list[str], missing: list[str]) -> str:
    lines = [
        "## Repo vend failed (evals)",
        "",
        "No GitHub repository was created.",
        "",
        "Add more context and/or labels, keep `repo-vend-approved`, status **In Review**, then re-run.",
        "",
        "Optional labels: `type-terraform` | `type-python`, `tf-module` | `tf-root`, "
        "`platform-aws` | `platform-gcp` | `platform-azure`.",
        "",
        "### Issues",
    ]
    for e in errors:
        lines.append(f"- {e}")
    for m in missing:
        lines.append(f"- Missing: {m}")
    lines.extend(
        [
            "",
            "### Naming",
            "- Terraform module: `terraform-module-<name>-<platform>`",
            "- Terraform root: `terraform-<name>`",
            "- Python: `python-<purpose-kebab>`",
            "- Always kebab-case",
        ]
    )
    return "\n".join(lines)


def _success_markdown(
    repo_name: str,
    repo_url: str,
    template: str,
    *,
    main_protected: bool,
) -> str:
    guardrail = (
        "Direct pushes to `main` are blocked (PR required)."
        if main_protected
        else (
            "Branch protection on `main` could **not** be applied — "
            "please configure it manually (PR required). "
            "Outcome label: `repo-vend-warning`."
        )
    )
    return "\n".join(
        [
            "## Repository vended",
            "",
            f"- **Name:** `{repo_name}`",
            f"- **URL:** [{repo_url}]({repo_url})",
            f"- **Template:** `{template}`",
            f"- **Guardrail:** {guardrail}",
            "",
            "Happy with the name? If not, comment e.g. "
            "`Please rename to python-better-name` and we will re-evaluate and rename.",
        ]
    )


def _error_plan(settings: Settings, markdown: str) -> JiraUpdatePlan:
    add, remove = _outcome_labels(settings, "error")
    return JiraUpdatePlan(
        transition_to=settings.jira_in_review_status,
        labels_add=add,
        labels_remove=remove,
        comment_markdown=markdown,
    )


def _success_plan(
    settings: Settings,
    *,
    outcome: str,
    markdown: str,
) -> JiraUpdatePlan:
    add, remove = _outcome_labels(settings, outcome)
    add = [*add, settings.jira_vended_label]
    return JiraUpdatePlan(
        transition_to=settings.jira_done_status,
        labels_add=add,
        labels_remove=remove,
        comment_markdown=markdown,
    )


def is_approved(issue: IssueSnapshot, settings: Settings) -> bool:
    return (
        issue.status.lower() == settings.jira_in_review_status.lower()
        and settings.jira_approved_label in issue.labels
    )


def is_vended(issue: IssueSnapshot, settings: Settings) -> bool:
    return settings.jira_vended_label in issue.labels


def vend_issue(issue: IssueSnapshot, settings: Settings | None = None) -> VendResult:
    """Run evals + GitHub create. Caller applies `result.jira` via Atlassian tools."""
    settings = settings or get_settings()
    key = issue.key
    with span("vend", issue_key=key):
        if is_vended(issue, settings):
            msg = (
                f"Issue {key} already has `{settings.jira_vended_label}`; "
                "skipping create (idempotent)."
            )
            record_vend(True, issue_key=key, skipped=True)
            return VendResult(
                success=True,
                outcome="skipped",
                issue_key=key,
                message=msg,
                skipped=True,
                jira=JiraUpdatePlan(
                    comment_markdown=f"## Vend skipped\n\n{msg}",
                ),
            )

        if not is_approved(issue, settings):
            msg = (
                f"HITL gate not satisfied: need status "
                f"`{settings.jira_in_review_status}` and label "
                f"`{settings.jira_approved_label}` "
                f"(status={issue.status}, labels={issue.labels})."
            )
            record_vend(False, issue_key=key, reason="hitl")
            return VendResult(
                success=False,
                outcome="error",
                issue_key=key,
                message=msg,
                jira=_error_plan(settings, f"## Vend blocked\n\n{msg}"),
            )

        harness = get_harness(settings)
        with span("extract", model=settings.orchestrator_model):
            intent = extract_intent_with_harness(
                harness,
                model=settings.orchestrator_model,
                summary=issue.summary,
                description=issue.description,
                labels=issue.labels,
            )

        with span("eval_llm", model=settings.eval_model):
            verdict = eval_with_harness(
                harness,
                model=settings.eval_model,
                intent=intent,
                summary=issue.summary,
                description=issue.description,
            )
        record_eval(verdict.passed, stage="llm", model=settings.eval_model)

        if verdict.proposed_name and not intent.proposed_name:
            intent.proposed_name = to_kebab(verdict.proposed_name)

        with span("eval_deterministic"):
            gate = validate_name_and_template(intent, settings)
        record_eval(gate.passed, stage="deterministic")

        if not verdict.passed or not gate.passed:
            errors = list(gate.errors)
            if not verdict.passed:
                errors.extend(verdict.reasons or ["LLM eval judge failed"])
            missing = list(dict.fromkeys([*intent.missing_info, *verdict.missing_info]))
            comment = _failure_markdown(errors, missing)
            record_vend(False, issue_key=key, reason="eval")
            return VendResult(
                success=False,
                outcome="error",
                issue_key=key,
                message=comment,
                jira=_error_plan(settings, comment),
            )

        assert gate.normalized_name and gate.template
        name = gate.normalized_name
        template = gate.template

        with GitHubClient(settings) as github:
            if github.repo_exists(name):
                msg = (
                    f"GitHub repo `{name}` already exists; not recreating. "
                    f"`{settings.jira_vended_label}` was not applied — pick a new "
                    "name or resolve the collision, then re-run."
                )
                record_vend(False, issue_key=key, reason="exists")
                return VendResult(
                    success=False,
                    outcome="error",
                    issue_key=key,
                    repo_name=name,
                    message=msg,
                    jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
                )

            try:
                created = github.create_from_template(
                    template=template,
                    name=name,
                    description=f"Vended from Jira {key}: {issue.summary}",
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"GitHub create-from-template failed: {exc}"
                record_vend(False, issue_key=key, reason="github_create")
                return VendResult(
                    success=False,
                    outcome="error",
                    issue_key=key,
                    message=msg,
                    jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
                )

            main_protected = github.protect_main(created.name)

        outcome = "success" if main_protected else "warning"
        markdown = _success_markdown(
            created.name,
            created.html_url,
            template,
            main_protected=main_protected,
        )
        record_vend(True, issue_key=key, repo=created.name, protected=main_protected)
        summary = (
            f"Created {created.html_url}"
            if main_protected
            else f"Created (warning: branch protection failed) {created.html_url}"
        )
        return VendResult(
            success=True,
            outcome=outcome,
            issue_key=key,
            repo_name=created.name,
            repo_url=created.html_url,
            template=template,
            message=summary,
            jira=_success_plan(settings, outcome=outcome, markdown=markdown),
        )


_RENAME_PATTERNS = [
    re.compile(r"rename\s+to\s+[`'\"]?([a-zA-Z0-9._/\- ]+)[`'\"]?", re.I),
    re.compile(r"new\s+name\s*:\s*[`'\"]?([a-zA-Z0-9._/\- ]+)[`'\"]?", re.I),
    re.compile(r"please\s+use\s+[`'\"]?([a-zA-Z0-9._/\- ]+)[`'\"]?", re.I),
]


def _parse_rename_candidate(text: str) -> str | None:
    for pat in _RENAME_PATTERNS:
        m = pat.search(text)
        if m:
            return to_kebab(m.group(1))
    for line in text.splitlines():
        line = line.strip().strip("`")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", line):
            if line.startswith(("terraform-", "python-")):
                return line
    return None


def rename_from_issue(
    issue: IssueSnapshot,
    *,
    current_name: str,
    comment_text: str,
    settings: Settings | None = None,
) -> VendResult:
    """Re-eval + GitHub rename. Caller applies `result.jira` via Atlassian tools."""
    settings = settings or get_settings()
    key = issue.key
    with span("rename", issue_key=key):
        if not is_vended(issue, settings):
            msg = f"Issue {key} is not marked `{settings.jira_vended_label}`."
            return VendResult(
                success=False,
                outcome="error",
                issue_key=key,
                message=msg,
                jira=_error_plan(settings, f"## Rename blocked\n\n{msg}"),
            )

        proposed = _parse_rename_candidate(comment_text)
        if not proposed:
            msg = (
                "Could not find a new repo name in the comment. "
                "Try: `Please rename to python-my-new-name`."
            )
            return VendResult(
                success=False,
                outcome="error",
                issue_key=key,
                message=msg,
                jira=_error_plan(settings, f"## Rename failed\n\n{msg}"),
            )

        harness = get_harness(settings)
        intent = extract_intent_with_harness(
            harness,
            model=settings.orchestrator_model,
            summary=issue.summary,
            description=f"{issue.description}\nRepo name: {proposed}",
            labels=issue.labels,
        )
        intent.proposed_name = proposed
        verdict = eval_with_harness(
            harness,
            model=settings.eval_model,
            intent=intent,
            summary=issue.summary,
            description=f"Rename request to {proposed}",
        )
        gate = validate_name_and_template(intent, settings)
        record_eval(verdict.passed and gate.passed, stage="rename")

        if not verdict.passed or not gate.passed:
            comment = _failure_markdown(
                gate.errors + (verdict.reasons or []),
                verdict.missing_info,
            )
            return VendResult(
                success=False,
                outcome="error",
                issue_key=key,
                message=comment,
                jira=_error_plan(settings, comment),
            )

        assert gate.normalized_name
        with GitHubClient(settings) as github:
            renamed = github.rename_repo(current_name, gate.normalized_name)
            main_protected = github.protect_main(renamed.name)

        outcome = "success" if main_protected else "warning"
        guardrail = (
            "Branch protection on `main` is in place (PR required)."
            if main_protected
            else (
                "Branch protection on `main` could **not** be applied; "
                "configure manually. Outcome: `repo-vend-warning`."
            )
        )
        markdown = "\n".join(
            [
                "## Repository renamed",
                "",
                f"- **Name:** `{renamed.name}`",
                f"- **URL:** [{renamed.html_url}]({renamed.html_url})",
                f"- **Guardrail:** {guardrail}",
                "",
                "Comment another name if you want a further rename.",
            ]
        )
        add, remove = _outcome_labels(settings, outcome)
        return VendResult(
            success=True,
            outcome=outcome,
            issue_key=key,
            repo_name=renamed.name,
            repo_url=renamed.html_url,
            template=gate.template,
            message=markdown,
            jira=JiraUpdatePlan(
                labels_add=add,
                labels_remove=remove,
                comment_markdown=markdown,
            ),
        )
