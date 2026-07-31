"""Propose / vend orchestration: evals + GitHub. Jira applied by Atlassian tools."""

from __future__ import annotations

import logging

from repo_vendor.approval import is_approval_comment
from repo_vendor.config import Settings, get_settings
from repo_vendor.github_client import GitHubClient
from repo_vendor.harness import eval_with_harness, extract_intent_with_harness, get_harness
from repo_vendor.models import (
    IssueSnapshot,
    JiraUpdatePlan,
    PhaseResult,
    SpecEvals,
    SpecRequest,
)
from repo_vendor.naming import to_kebab, validate_name_and_template
from repo_vendor.observability import record_eval, record_vend, span
from repo_vendor.readme_gen import build_vended_readme
from repo_vendor.spec import request_rel_path, spec_from_yaml, spec_to_yaml

logger = logging.getLogger(__name__)


def _outcome_labels(settings: Settings, outcome: str) -> tuple[list[str], list[str]]:
    success = settings.jira_label_success
    warning = settings.jira_label_warning
    error = settings.jira_label_error
    all_outcomes = [success, warning, error]
    chosen = {"success": success, "warning": warning, "error": error}[outcome]
    return [chosen], [lbl for lbl in all_outcomes if lbl != chosen]


def _failure_markdown(errors: list[str], missing: list[str]) -> str:
    lines = [
        "## Repo vend proposal failed (evals)",
        "",
        "No Spec Request PR was opened and no GitHub repository will be created.",
        "",
        "Add more context and/or labels, then create a new ticket or re-trigger **propose**.",
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
            "",
            "See `rules/naming.md`.",
        ]
    )
    return "\n".join(lines)


def _proposal_markdown(
    *,
    issue_key: str,
    proposed_name: str,
    template: str,
    llm_passed: bool,
    deterministic_passed: bool,
    reasons: list[str],
    missing: list[str],
    pr_url: str | None,
) -> str:
    eval_ok = llm_passed and deterministic_passed
    indicator = "PASSED" if eval_ok else "FAILED"
    lines = [
        "## Repo vend proposal",
        "",
        f"**Evals:** `{indicator}` (LLM={'pass' if llm_passed else 'fail'}, "
        f"deterministic={'pass' if deterministic_passed else 'fail'})",
        "",
        f"- **Issue:** `{issue_key}`",
        f"- **Proposed name:** `{proposed_name}`",
        f"- **Template:** `{template}`",
    ]
    if pr_url:
        lines.append(f"- **Spec Request PR:** [{pr_url}]({pr_url})")
    if reasons:
        lines.extend(["", "### Reasons", *[f"- {r}" for r in reasons]])
    if missing:
        lines.extend(["", "### Missing", *[f"- {m}" for m in missing]])
    lines.extend(
        [
            "",
            "### Approve",
            "Reply with one of: `approved`, `lgtm`, `looks good`, `ship it`, or `+1`.",
            "That merges the Spec (if open) and creates the GitHub repository.",
            "There is no post-create rename — fix the ticket and re-propose if the name is wrong.",
        ]
    )
    return "\n".join(lines)


def _success_markdown(
    repo_name: str,
    repo_url: str,
    template: str,
    *,
    main_protected: bool,
    readme_updated: bool = True,
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
    readme_line = (
        "Project README was written for this repository (template boilerplate replaced)."
        if readme_updated
        else (
            "Could **not** rewrite README.md after create — "
            "please replace the template README manually. Outcome: `repo-vend-warning`."
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
            f"- **README:** {readme_line}",
            "",
            "Name changes after create are not supported — open a new Repo Vend Request if needed.",
        ]
    )


def _error_plan(settings: Settings, markdown: str) -> JiraUpdatePlan:
    add, remove = _outcome_labels(settings, "error")
    return JiraUpdatePlan(
        transition_to=None,
        labels_add=add,
        labels_remove=[*remove, settings.jira_proposed_label],
        comment_markdown=markdown,
    )


def _success_vend_plan(
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
        labels_remove=[*remove, settings.jira_proposed_label],
        comment_markdown=markdown,
    )


def is_vended(issue: IssueSnapshot, settings: Settings) -> bool:
    return settings.jira_vended_label in issue.labels


def propose_issue(issue: IssueSnapshot, settings: Settings | None = None) -> PhaseResult:
    """Run evals; on pass open Spec Request PR and return Jira proposal plan."""
    settings = settings or get_settings()
    key = issue.key
    with span("propose", issue_key=key):
        if is_vended(issue, settings):
            msg = f"Issue {key} already has `{settings.jira_vended_label}`; skipping propose."
            return PhaseResult(
                success=True,
                outcome="skipped",
                phase="propose",
                issue_key=key,
                message=msg,
                skipped=True,
                jira=JiraUpdatePlan(comment_markdown=f"## Propose skipped\n\n{msg}"),
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

        errors = list(gate.errors)
        if not verdict.passed:
            errors.extend(verdict.reasons or ["LLM eval judge failed"])
        missing = list(dict.fromkeys([*intent.missing_info, *verdict.missing_info]))

        if not verdict.passed or not gate.passed:
            comment = _failure_markdown(errors, missing)
            record_vend(False, issue_key=key, reason="eval_propose")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="propose",
                issue_key=key,
                message=comment,
                jira=_error_plan(settings, comment),
            )

        assert gate.normalized_name and gate.template
        name = gate.normalized_name
        template = gate.template
        path = request_rel_path(key)
        spec = SpecRequest(
            issue_key=key,
            summary=issue.summary,
            description=issue.description,
            intent=intent.model_dump(mode="json"),
            proposed_name=name,
            template=template,
            evals=SpecEvals(
                llm_passed=True,
                deterministic_passed=True,
                reasons=list(verdict.reasons or []),
                missing_info=missing,
            ),
            status="proposed",
        )

        pr_url: str | None = None
        try:
            with GitHubClient(settings) as github:
                pr = github.open_spec_pr(
                    issue_key=key,
                    path=path,
                    content=spec_to_yaml(spec),
                )
                pr_url = pr.html_url
                spec.pr_url = pr_url
                # Refresh file on branch with pr_url filled
                github.put_file(
                    path=path,
                    content=spec_to_yaml(spec),
                    branch=f"propose/{key}",
                    message=f"Record Spec PR URL for {key}",
                )
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to open Spec Request PR: {exc}"
            record_vend(False, issue_key=key, reason="spec_pr")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="propose",
                issue_key=key,
                proposed_name=name,
                template=template,
                request_path=path,
                message=msg,
                jira=_error_plan(settings, f"## Propose failed\n\n{msg}"),
            )

        markdown = _proposal_markdown(
            issue_key=key,
            proposed_name=name,
            template=template,
            llm_passed=True,
            deterministic_passed=True,
            reasons=list(verdict.reasons or []),
            missing=missing,
            pr_url=pr_url,
        )
        record_vend(True, issue_key=key, repo=name, phase="propose")
        return PhaseResult(
            success=True,
            outcome="success",
            phase="propose",
            issue_key=key,
            proposed_name=name,
            template=template,
            request_path=path,
            pr_url=pr_url,
            message=f"Proposal ready for {name}",
            jira=JiraUpdatePlan(
                transition_to=None,
                labels_add=[settings.jira_proposed_label],
                labels_remove=[settings.jira_label_error],
                comment_markdown=markdown,
            ),
        )


def vend_issue(
    issue: IssueSnapshot,
    *,
    approval_comment: str | None = None,
    settings: Settings | None = None,
) -> PhaseResult:
    """Merge Spec if needed, load requests/<key>.yaml, create-from-template."""
    settings = settings or get_settings()
    key = issue.key
    with span("vend", issue_key=key):
        if is_vended(issue, settings):
            msg = (
                f"Issue {key} already has `{settings.jira_vended_label}`; "
                "skipping create (idempotent)."
            )
            record_vend(True, issue_key=key, skipped=True)
            return PhaseResult(
                success=True,
                outcome="skipped",
                phase="vend",
                issue_key=key,
                message=msg,
                skipped=True,
                jira=JiraUpdatePlan(comment_markdown=f"## Vend skipped\n\n{msg}"),
            )

        if not is_approval_comment(approval_comment):
            msg = (
                "Keyword Approval required. Reply with `approved`, `lgtm`, "
                "`looks good`, `ship it`, or `+1`."
            )
            record_vend(False, issue_key=key, reason="keyword")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="vend",
                issue_key=key,
                message=msg,
                jira=_error_plan(settings, f"## Vend blocked\n\n{msg}"),
            )

        path = request_rel_path(key)
        try:
            with GitHubClient(settings) as github:
                github.ensure_spec_merged(key)
                try:
                    raw = github.get_file_text(path)
                except FileNotFoundError:
                    # dry-run / local fallback
                    from repo_vendor.spec import request_local_path

                    local = request_local_path(key)
                    if not local.is_file():
                        raise
                    raw = local.read_text(encoding="utf-8")

                spec = spec_from_yaml(raw)
                name = spec.proposed_name
                template = spec.template

                if github.repo_exists(name):
                    msg = (
                        f"GitHub repo `{name}` already exists; not recreating. "
                        f"`{settings.jira_vended_label}` was not applied."
                    )
                    record_vend(False, issue_key=key, reason="exists")
                    return PhaseResult(
                        success=False,
                        outcome="error",
                        phase="vend",
                        issue_key=key,
                        repo_name=name,
                        template=template,
                        request_path=path,
                        message=msg,
                        jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
                    )

                try:
                    created = github.create_from_template(
                        template=template,
                        name=name,
                        description=f"Vended from Jira {key}: {spec.summary}",
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = f"GitHub create-from-template failed: {exc}"
                    record_vend(False, issue_key=key, reason="github_create")
                    return PhaseResult(
                        success=False,
                        outcome="error",
                        phase="vend",
                        issue_key=key,
                        message=msg,
                        jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
                    )

                main_protected = github.protect_main(created.name)
                readme = build_vended_readme(
                    repo_name=created.name,
                    summary=spec.summary,
                    description=spec.description,
                    issue_key=key,
                    template=template,
                    repo_url=created.html_url,
                )
                readme_ok = github.write_vended_readme(
                    repo_name=created.name,
                    content=readme,
                )
        except FileNotFoundError:
            msg = (
                f"Spec Request `{path}` not found on the control-plane repo. "
                "Run **propose** first and ensure the Spec PR is mergeable."
            )
            record_vend(False, issue_key=key, reason="missing_spec")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="vend",
                issue_key=key,
                request_path=path,
                message=msg,
                jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Vend failed while loading Spec / GitHub: {exc}"
            record_vend(False, issue_key=key, reason="vend_exc")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="vend",
                issue_key=key,
                message=msg,
                jira=_error_plan(settings, f"## Vend failed\n\n{msg}"),
            )

        outcome = "success" if main_protected and readme_ok else "warning"
        markdown = _success_markdown(
            created.name,
            created.html_url,
            template,
            main_protected=main_protected,
            readme_updated=readme_ok,
        )
        record_vend(True, issue_key=key, repo=created.name, protected=main_protected)
        summary = (
            f"Created {created.html_url}"
            if main_protected
            else f"Created (warning: branch protection failed) {created.html_url}"
        )
        return PhaseResult(
            success=True,
            outcome=outcome,
            phase="vend",
            issue_key=key,
            repo_name=created.name,
            repo_url=created.html_url,
            template=template,
            proposed_name=name,
            request_path=path,
            message=summary,
            jira=_success_vend_plan(settings, outcome=outcome, markdown=markdown),
        )
