"""PydanticAI orchestration for vend and rename flows."""

from __future__ import annotations

import logging
import re

from repo_vendor.config import Settings, get_settings
from repo_vendor.github_client import GitHubClient
from repo_vendor.harness import eval_with_harness, extract_intent_with_harness, get_harness
from repo_vendor.jira_client import JiraClient
from repo_vendor.models import VendResult
from repo_vendor.naming import to_kebab, validate_name_and_template
from repo_vendor.observability import record_eval, record_vend, span

logger = logging.getLogger(__name__)


def _failure_comment(errors: list[str], missing: list[str]) -> str:
    lines = [
        "Repo vend eval checks did not pass — no repository was created.",
        "",
        "Please add more context in the description and/or use labels, then keep "
        "`repo-vend-approved` while the ticket stays In Review so we can re-evaluate.",
        "",
        "Helpful labels (optional): `type-terraform` | `type-python`, "
        "`tf-module` | `tf-root`, `platform-aws` | `platform-gcp` | `platform-azure`.",
        "",
        "Issues:",
    ]
    for e in errors:
        lines.append(f"- {e}")
    for m in missing:
        lines.append(f"- Missing: {m}")
    lines.extend(
        [
            "",
            "Naming reminders:",
            "- Terraform module: `terraform-module-<name>-<platform>`",
            "- Terraform root: `terraform-<name>`",
            "- Python: `python-<purpose-kebab>`",
            "- All names are kebab-case (we normalize snake_case/spaces).",
        ]
    )
    return "\n".join(lines)


def _success_comment(
    repo_name: str,
    repo_url: str,
    template: str,
    *,
    main_protected: bool = True,
) -> str:
    guardrail = (
        "- Guardrail: direct pushes to `main` are blocked (PR required)."
        if main_protected
        else (
            "- Guardrail: branch protection on `main` could not be applied; "
            "please configure it manually (PR required)."
        )
    )
    return (
        f"Repository vended successfully.\n\n"
        f"- Name: `{repo_name}`\n"
        f"- URL: {repo_url}\n"
        f"- Template: `{template}`\n"
        f"{guardrail}\n\n"
        f"Are you happy with the repo name? If not, please comment a new kebab-case "
        f"name (for example: `Please rename to python-better-name`) and we will "
        f"re-evaluate and rename."
    )


def scan_and_vend(settings: Settings | None = None, *, max_issues: int = 10) -> list[VendResult]:
    """Poll Jira for approved, not-yet-vended issues and vend each (cron-friendly)."""
    settings = settings or get_settings()
    results: list[VendResult] = []
    with span("scan", max_issues=max_issues):
        with JiraClient(settings) as jira:
            pending = jira.search_approved_pending(max_results=max_issues)
        if not pending:
            logger.info("scan: no approved pending issues")
            return results
        for issue in pending:
            results.append(vend_issue(issue.key, settings))
    return results


def vend_issue(issue_key: str, settings: Settings | None = None) -> VendResult:
    settings = settings or get_settings()
    with span("vend", issue_key=issue_key):
        with JiraClient(settings) as jira, GitHubClient(settings) as github:
            issue = jira.get_issue(issue_key)

            if jira.is_vended(issue):
                msg = (
                    f"Issue {issue_key} already has `{settings.jira_vended_label}`; "
                    "skipping create (idempotent)."
                )
                record_vend(True, issue_key=issue_key, skipped=True)
                return VendResult(
                    success=True,
                    issue_key=issue_key,
                    message=msg,
                    skipped=True,
                )

            if not jira.is_approved(issue):
                msg = (
                    f"HITL gate not satisfied: need status "
                    f"`{settings.jira_in_review_status}` and label "
                    f"`{settings.jira_approved_label}` "
                    f"(status={issue.status}, labels={issue.labels})."
                )
                jira.add_comment(issue_key, msg)
                record_vend(False, issue_key=issue_key, reason="hitl")
                return VendResult(success=False, issue_key=issue_key, message=msg)

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

            # Merge LLM proposed name into intent when present
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
                comment = _failure_comment(errors, missing)
                jira.add_comment(issue_key, comment)
                record_vend(False, issue_key=issue_key, reason="eval")
                return VendResult(success=False, issue_key=issue_key, message=comment)

            assert gate.normalized_name and gate.template
            name = gate.normalized_name
            template = gate.template

            if github.repo_exists(name):
                msg = (
                    f"GitHub repo `{name}` already exists; not recreating. "
                    f"`{settings.jira_vended_label}` was not applied — pick a new "
                    "name or resolve the collision, then re-run."
                )
                jira.add_comment(issue_key, msg)
                record_vend(False, issue_key=issue_key, reason="exists")
                return VendResult(
                    success=False,
                    issue_key=issue_key,
                    repo_name=name,
                    message=msg,
                )

            created = github.create_from_template(
                template=template,
                name=name,
                description=f"Vended from Jira {issue_key}: {issue.summary}",
            )
            main_protected = github.protect_main(created.name)
            jira.add_comment(
                issue_key,
                _success_comment(
                    created.name,
                    created.html_url,
                    template,
                    main_protected=main_protected,
                ),
            )
            jira.add_label(issue_key, settings.jira_vended_label)
            record_vend(True, issue_key=issue_key, repo=created.name)
            return VendResult(
                success=True,
                issue_key=issue_key,
                repo_name=created.name,
                repo_url=created.html_url,
                template=template,
                message=f"Created {created.html_url}",
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
    # bare kebab line
    for line in text.splitlines():
        line = line.strip().strip("`")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", line):
            if line.startswith(("terraform-", "python-")):
                return line
    return None


def rename_from_issue(
    issue_key: str,
    *,
    current_name: str,
    comment_text: str,
    settings: Settings | None = None,
) -> VendResult:
    """Re-eval a proposed rename and rename on GitHub if checks pass."""
    settings = settings or get_settings()
    with span("rename", issue_key=issue_key):
        with JiraClient(settings) as jira, GitHubClient(settings) as github:
            issue = jira.get_issue(issue_key)
            if not jira.is_vended(issue):
                msg = f"Issue {issue_key} is not marked `{settings.jira_vended_label}`."
                jira.add_comment(issue_key, msg)
                return VendResult(success=False, issue_key=issue_key, message=msg)

            proposed = _parse_rename_candidate(comment_text)
            if not proposed:
                msg = (
                    "Could not find a new repo name in the comment. "
                    "Try: `Please rename to python-my-new-name`."
                )
                jira.add_comment(issue_key, msg)
                return VendResult(success=False, issue_key=issue_key, message=msg)

            # Build intent from labels + proposed name
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
                comment = _failure_comment(
                    gate.errors + (verdict.reasons or []),
                    verdict.missing_info,
                )
                jira.add_comment(issue_key, comment)
                return VendResult(success=False, issue_key=issue_key, message=comment)

            assert gate.normalized_name
            renamed = github.rename_repo(current_name, gate.normalized_name)
            main_protected = github.protect_main(renamed.name)
            guardrail = (
                "Branch protection on `main` is in place (PR required)."
                if main_protected
                else (
                    "Branch protection on `main` could not be applied; "
                    "please configure it manually."
                )
            )
            msg = (
                f"Renamed repository to `{renamed.name}`.\n"
                f"URL: {renamed.html_url}\n"
                f"{guardrail}\n\n"
                f"Are you happy with the repo name? If not, comment another name."
            )
            jira.add_comment(issue_key, msg)
            return VendResult(
                success=True,
                issue_key=issue_key,
                repo_name=renamed.name,
                repo_url=renamed.html_url,
                template=gate.template,
                message=msg,
            )
