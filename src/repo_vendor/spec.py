"""Spec Request YAML helpers (requests/<ISSUE-KEY>.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml

from repo_vendor.models import SpecRequest
from repo_vendor.prompts import find_repo_root

_MAX_DESC_CHARS = 1200


def request_rel_path(issue_key: str) -> str:
    return f"requests/{issue_key}.yaml"


def request_local_path(issue_key: str, root: Path | None = None) -> Path:
    base = root or find_repo_root()
    return base / request_rel_path(issue_key)


def spec_to_yaml(spec: SpecRequest) -> str:
    data = spec.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def spec_from_yaml(text: str) -> SpecRequest:
    data = yaml.safe_load(text) or {}
    return SpecRequest.model_validate(data)


def write_spec_local(spec: SpecRequest, root: Path | None = None) -> Path:
    path = request_local_path(spec.issue_key, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spec_to_yaml(spec), encoding="utf-8")
    return path


def format_spec_pr_title(spec: SpecRequest) -> str:
    """Human-readable Spec PR title (what will be vended)."""
    name = (spec.proposed_name or "").strip() or "unnamed"
    return f"Propose `{name}` ({spec.issue_key})"


def format_spec_pr_body(
    spec: SpecRequest,
    *,
    jira_base_url: str = "",
) -> str:
    """Markdown body summarizing the frozen propose output for GitHub reviewers."""
    intent = spec.intent or {}
    project_type = intent.get("project_type") or "unknown"
    shape = intent.get("terraform_shape")
    platform = intent.get("platform")
    purpose = intent.get("purpose")
    confidence = intent.get("confidence")

    base = (jira_base_url or "").rstrip("/")
    issue_ref = (
        f"[{spec.issue_key}]({base}/browse/{spec.issue_key})"
        if base
        else f"`{spec.issue_key}`"
    )

    summary = (spec.summary or "").strip() or "(none)"
    description = (spec.description or "").strip() or "(no description)"
    if len(description) > _MAX_DESC_CHARS:
        description = description[: _MAX_DESC_CHARS].rstrip() + "\n\n_(truncated)_"

    llm = "pass" if spec.evals.llm_passed else "fail"
    det = "pass" if spec.evals.deterministic_passed else "fail"
    eval_ok = spec.evals.llm_passed and spec.evals.deterministic_passed

    lines = [
        f"## Propose `{spec.proposed_name}`",
        "",
        f"Frozen Spec Request for Jira {issue_ref}.",
        "",
        "| | |",
        "| --- | --- |",
        f"| **Proposed name** | `{spec.proposed_name}` |",
        f"| **Template** | `{spec.template}` |",
        f"| **Project type** | `{project_type}` |",
    ]
    if shape:
        lines.append(f"| **Terraform shape** | `{shape}` |")
    if platform:
        lines.append(f"| **Platform** | `{platform}` |")
    if purpose:
        lines.append(f"| **Purpose** | `{purpose}` |")
    if confidence is not None and confidence != "":
        lines.append(f"| **Confidence** | `{confidence}` |")
    lines.extend(
        [
            f"| **Evals** | `{'PASSED' if eval_ok else 'FAILED'}` "
            f"(LLM={llm}, deterministic={det}) |",
            "",
            "### Ticket summary",
            "",
            summary,
            "",
            "### Ticket description",
            "",
            description,
        ]
    )
    if spec.evals.reasons:
        lines.extend(
            ["", "### Eval reasons", *[f"- {r}" for r in spec.evals.reasons]]
        )
    if spec.evals.missing_info:
        lines.extend(
            [
                "",
                "### Missing info",
                *[f"- {m}" for m in spec.evals.missing_info],
            ]
        )
    lines.extend(
        [
            "",
            "### Next step",
            "",
            "Merge on **Keyword Approval** (`approved` / `lgtm` / `looks good` / "
            "`ship it` / `+1`) — the vend automation merges this PR and creates "
            "the GitHub repository from the template. There is no post-create rename.",
        ]
    )
    return "\n".join(lines)
