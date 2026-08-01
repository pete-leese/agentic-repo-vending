"""Propose / vend orchestration: evals + GitHub. Jira applied by Atlassian tools."""

from __future__ import annotations

import logging
from typing import Literal

from repo_vendor.approval import is_approval_comment
from repo_vendor.config import Settings, get_settings
from repo_vendor.cursor_run import format_cursor_agent_line, resolve_cursor_agent
from repo_vendor.github_client import GitHubClient
from repo_vendor.harness import (
    derive_confidence,
    eval_with_harness,
    extract_intent_with_harness,
    get_harness,
)
from repo_vendor.models import (
    IssueSnapshot,
    JiraUpdatePlan,
    PhaseResult,
    SpecEvals,
    SpecRequest,
)
from repo_vendor.naming import (
    enrich_intent_from_heuristics,
    enrich_intent_platform,
    enrich_intent_type_and_shape,
    reconcile_intent_from_proposed_name,
    to_kebab,
    validate_name_and_template,
)
from repo_vendor.observability import record_eval, record_vend, span
from repo_vendor.readme_gen import resolve_vended_readme
from repo_vendor.spec import (
    format_spec_pr_body,
    format_spec_pr_title,
    request_rel_path,
    resolve_create_name_from_spec,
    spec_from_yaml,
    spec_to_yaml,
)

logger = logging.getLogger(__name__)


def _outcome_labels(settings: Settings, outcome: str) -> tuple[list[str], list[str]]:
    success = settings.jira_label_success
    warning = settings.jira_label_warning
    error = settings.jira_label_error
    all_outcomes = [success, warning, error]
    chosen = {"success": success, "warning": warning, "error": error}[outcome]
    return [chosen], [lbl for lbl in all_outcomes if lbl != chosen]


def _meta_lines(
    *,
    confidence: float | None = None,
    cursor_agent_id: str | None = None,
    cursor_agent_url: str | None = None,
) -> list[str]:
    lines: list[str] = []
    if confidence is not None:
        lines.append(f"- **Confidence:** `{confidence:.2f}`")
    agent_line = format_cursor_agent_line(agent_id=cursor_agent_id, agent_url=cursor_agent_url)
    if agent_line:
        lines.append(agent_line)
    return lines


def _failure_markdown(
    errors: list[str],
    missing: list[str],
    *,
    confidence: float | None = None,
    cursor_agent_id: str | None = None,
    cursor_agent_url: str | None = None,
) -> str:
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
    meta = _meta_lines(
        confidence=confidence,
        cursor_agent_id=cursor_agent_id,
        cursor_agent_url=cursor_agent_url,
    )
    if meta:
        lines.extend(["", "### Run", *meta])
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
    confidence: float | None = None,
    cursor_agent_id: str | None = None,
    cursor_agent_url: str | None = None,
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
    lines.extend(
        _meta_lines(
            confidence=confidence,
            cursor_agent_id=cursor_agent_id,
            cursor_agent_url=cursor_agent_url,
        )
    )
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
            "Reply to this proposal (or add a new top-level comment) with one of: "
            "`approved`, `lgtm`, `looks good`, `ship it`, or `+1`.",
            "Threaded replies are fine — the keyword only needs to appear in your reply text.",
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
    cursor_agent_id: str | None = None,
    cursor_agent_url: str | None = None,
) -> str:
    guardrail = (
        "Classic branch protection on `main` is enabled (PR + 1 review required; admins enforced)."
        if main_protected
        else (
            "Classic branch protection on `main` could **not** be applied — "
            "configure **Settings → Branches → Add classic branch protection rule** "
            "(not rulesets) for `main`, or ensure `GITHUB_TOKEN` has admin "
            "(classic `repo` / fine-grained Administration: write). "
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
    lines = [
        "## Repository vended",
        "",
        f"- **Name:** `{repo_name}`",
        f"- **URL:** [{repo_url}]({repo_url})",
        f"- **Template:** `{template}`",
        f"- **Guardrail:** {guardrail}",
        f"- **README:** {readme_line}",
    ]
    lines.extend(
        _meta_lines(
            cursor_agent_id=cursor_agent_id,
            cursor_agent_url=cursor_agent_url,
        )
    )
    lines.extend(
        [
            "",
            "Name changes after create are not supported — open a new Repo Vend Request if needed.",
        ]
    )
    return "\n".join(lines)


def _approved_work_description(
    *,
    issue_key: str,
    spec: SpecRequest,
    repo_name: str,
    repo_url: str,
    outcome: str,
) -> str:
    """Board Description after Keyword Approval + vend — what was approved/performed."""
    intent = spec.intent or {}
    project_type = intent.get("project_type") or "unknown"
    shape = intent.get("terraform_shape")
    platform = intent.get("platform")
    purpose = intent.get("purpose")
    lines = [
        f"## Approved repo vend ({issue_key})",
        "",
        "Keyword Approval accepted. The following was performed:",
        "",
        f"- **Repository:** [{repo_name}]({repo_url})",
        f"- **Template:** `{spec.template}`",
        f"- **Project type:** `{project_type}`",
    ]
    if shape:
        lines.append(f"- **Terraform shape:** `{shape}`")
    if platform:
        lines.append(f"- **Platform:** `{platform}`")
    if purpose:
        lines.append(f"- **Purpose:** `{purpose}`")
    lines.extend(
        [
            f"- **Outcome:** `{outcome}`",
            "",
            "### Original request",
            "",
            f"**Summary:** {spec.summary or '(none)'}",
            "",
            spec.description.strip() or "(no original description)",
            "",
            "---",
            "Post-create rename is not supported. Open a new Repo Vend Request to change the name.",
        ]
    )
    return "\n".join(lines)


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
    set_description: str | None = None,
) -> JiraUpdatePlan:
    add, remove = _outcome_labels(settings, outcome)
    add = [*add, settings.jira_vended_label]
    return JiraUpdatePlan(
        transition_to=settings.jira_done_status,
        labels_add=add,
        labels_remove=[*remove, settings.jira_proposed_label],
        comment_markdown=markdown,
        set_description=set_description,
    )


def _proposal_ready_plan(settings: Settings, markdown: str) -> JiraUpdatePlan:
    """Proposal ready: add repo-vend-proposed, clear prior error-state outcome labels."""
    error_states = [
        settings.jira_label_error,
        settings.jira_label_warning,
        settings.jira_label_success,
    ]
    return JiraUpdatePlan(
        transition_to=None,
        labels_add=[settings.jira_proposed_label],
        labels_remove=error_states,
        comment_markdown=markdown,
    )


def is_vended(issue: IssueSnapshot, settings: Settings) -> bool:
    return settings.jira_vended_label in issue.labels


def propose_issue(
    issue: IssueSnapshot,
    settings: Settings | None = None,
    *,
    cursor_agent_id: str | None = None,
) -> PhaseResult:
    """Run evals; on pass open Spec Request PR and return Jira proposal plan."""
    settings = settings or get_settings()
    key = issue.key
    agent_id, agent_url = resolve_cursor_agent(agent_id=cursor_agent_id)
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
            intent = enrich_intent_from_heuristics(
                intent,
                issue.summary,
                issue.description,
                issue.labels,
            )
            intent = enrich_intent_platform(
                intent,
                summary=issue.summary,
                description=issue.description,
                labels=issue.labels,
            )
            intent = enrich_intent_type_and_shape(
                intent,
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
        intent = reconcile_intent_from_proposed_name(intent)

        with span("eval_deterministic"):
            gate = validate_name_and_template(intent, settings)
        record_eval(gate.passed, stage="deterministic")

        errors = list(gate.errors)
        if not verdict.passed:
            errors.extend(verdict.reasons or ["LLM eval judge failed"])
        missing = list(dict.fromkeys([*intent.missing_info, *verdict.missing_info]))

        if not verdict.passed or not gate.passed:
            intent.confidence = derive_confidence(intent, gate_passed=False)
            comment = _failure_markdown(
                errors,
                missing,
                confidence=intent.confidence,
                cursor_agent_id=agent_id,
                cursor_agent_url=agent_url,
            )
            record_vend(False, issue_key=key, reason="eval_propose")
            return PhaseResult(
                success=False,
                outcome="error",
                phase="propose",
                issue_key=key,
                message=comment,
                confidence=intent.confidence,
                cursor_agent_id=agent_id,
                cursor_agent_url=agent_url,
                jira=_error_plan(settings, comment),
            )

        assert gate.normalized_name and gate.template
        name = gate.normalized_name
        template = gate.template
        # Keep Spec intent + top-level proposed_name in lockstep with the gate name.
        intent.proposed_name = name
        intent = reconcile_intent_from_proposed_name(intent)
        intent.confidence = derive_confidence(intent, gate_passed=True)
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
                    title=format_spec_pr_title(spec),
                    body=format_spec_pr_body(spec, jira_base_url=settings.jira_base_url),
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
                confidence=intent.confidence,
                cursor_agent_id=agent_id,
                cursor_agent_url=agent_url,
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
            confidence=intent.confidence,
            cursor_agent_id=agent_id,
            cursor_agent_url=agent_url,
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
            confidence=intent.confidence,
            cursor_agent_id=agent_id,
            cursor_agent_url=agent_url,
            jira=_proposal_ready_plan(settings, markdown),
        )


def vend_issue(
    issue: IssueSnapshot,
    *,
    approval_comment: str | None = None,
    settings: Settings | None = None,
    cursor_agent_id: str | None = None,
) -> PhaseResult:
    """Merge Spec if needed, load requests/<key>.yaml, create-from-template."""
    settings = settings or get_settings()
    key = issue.key
    agent_id, agent_url = resolve_cursor_agent(agent_id=cursor_agent_id)
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
                # Spec is SoR: resolve create name from intent (not a polluted top-level typo).
                name, resolved_template = resolve_create_name_from_spec(spec, settings)
                template = spec.template or resolved_template
                spec.proposed_name = name

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

                # Template generate is async — wait for main before mutating it.
                if not github.wait_for_branch(created.name, "main"):
                    logger.warning(
                        "main not ready after template generate for %s; continuing",
                        created.name,
                    )
                # README must be written *before* classic protection with
                # enforce_admins=true (otherwise the bot cannot push to main).
                template_readme: str | None = None
                try:
                    template_readme = github.get_file_text("README.md", repo=created.name)
                except FileNotFoundError:
                    template_readme = None
                readme = resolve_vended_readme(
                    template_readme,
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
                # Classic branch protection (PUT .../branches/main/protection), not rulesets.
                main_protected = github.protect_main(created.name)
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

        outcome: Literal["success", "warning"] = (
            "success" if main_protected and readme_ok else "warning"
        )
        markdown = _success_markdown(
            created.name,
            created.html_url,
            template,
            main_protected=main_protected,
            readme_updated=readme_ok,
            cursor_agent_id=agent_id,
            cursor_agent_url=agent_url,
        )
        record_vend(True, issue_key=key, repo=created.name, protected=main_protected)
        summary = (
            f"Created {created.html_url}"
            if main_protected
            else f"Created (warning: branch protection failed) {created.html_url}"
        )
        description = _approved_work_description(
            issue_key=key,
            spec=spec,
            repo_name=created.name,
            repo_url=created.html_url,
            outcome=outcome,
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
            cursor_agent_id=agent_id,
            cursor_agent_url=agent_url,
            jira=_success_vend_plan(
                settings,
                outcome=outcome,
                markdown=markdown,
                set_description=description,
            ),
        )
