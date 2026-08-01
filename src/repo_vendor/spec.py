"""Spec Request YAML helpers (requests/<ISSUE-KEY>.yaml)."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import ExtractedIntent, SpecRequest
from repo_vendor.naming import (
    GENERIC_NAME,
    PYTHON_NAME,
    TF_MODULE,
    TF_ROOT,
    build_proposed_name,
    clean_purpose_slug,
    select_template,
    to_kebab,
    validate_name_and_template,
)
from repo_vendor.prompts import find_repo_root

logger = logging.getLogger(__name__)
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


def _is_canonical_repo_name(name: str) -> bool:
    return bool(
        TF_MODULE.fullmatch(name)
        or TF_ROOT.fullmatch(name)
        or PYTHON_NAME.fullmatch(name)
        or GENERIC_NAME.fullmatch(name)
    )


def resolve_create_name_from_spec(
    spec: SpecRequest,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Resolve ``(repo_name, template)`` for create-from-template from Spec.

    Spec is the system of record. Prefer a canonical ``intent.proposed_name`` over a
    polluted top-level ``proposed_name`` (REPO-15: intent had ``terraform-module-gke-gcp``
    while top-level was rebuilt as ``terraform-module-give-me-gke-gcp``), then rebuild
    via the deterministic gate so purpose filler cannot win.
    """
    settings = settings or get_settings()
    intent = ExtractedIntent.model_validate(spec.intent or {})
    top = to_kebab(spec.proposed_name) if spec.proposed_name else None
    inner = to_kebab(intent.proposed_name) if intent.proposed_name else None

    # Prefer intent.proposed_name when it is already a valid repo name.
    chosen: str | None = None
    for candidate in (inner, top):
        if candidate and _is_canonical_repo_name(candidate):
            chosen = candidate
            break
    if chosen:
        intent.proposed_name = chosen
    elif top:
        intent.proposed_name = top

    if intent.purpose:
        cleaned = clean_purpose_slug(intent.purpose)
        if cleaned:
            intent.purpose = cleaned

    gate = validate_name_and_template(intent, settings)
    if gate.passed and gate.normalized_name:
        template = gate.template or spec.template
        return gate.normalized_name, template

    built = build_proposed_name(intent)
    if built:
        if intent.project_type is not None:
            template = select_template(intent.project_type, settings)
        else:
            template = spec.template
        return built, template or spec.template

    if not top:
        raise ValueError(
            f"Spec {spec.issue_key} has no usable proposed_name for create-from-template"
        )
    return top, spec.template


def format_spec_pr_title(spec: SpecRequest) -> str:
    """Human-readable Spec PR title (what will be vended)."""
    name = (spec.proposed_name or "").strip() or "unnamed"
    return f"Propose `{name}` ({spec.issue_key})"


def load_specs_from_requests_dir(root: Path | None = None) -> list[SpecRequest]:
    """Load Spec Requests from ``requests/*.yaml`` under the control-plane checkout."""
    base = (root or find_repo_root()) / "requests"
    if not base.is_dir():
        return []
    specs: list[SpecRequest] = []
    for path in sorted(base.glob("*.yaml")):
        if path.name.upper() == "README.YAML":
            continue
        try:
            specs.append(spec_from_yaml(path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            # Skip unreadable / invalid Specs; do not block propose on one bad file.
            logger.warning("Skipping Spec %s: %s", path, exc)
    return specs


def find_duplicate_proposed_name(
    proposed_name: str,
    *,
    issue_key: str,
    specs: list[SpecRequest],
) -> SpecRequest | None:
    """Return another Spec that already claims ``proposed_name`` (case/kebab-normalized).

    The same ``issue_key`` is ignored so re-propose of the same ticket is allowed.
    """
    target = to_kebab(proposed_name)
    if not target:
        return None
    self_key = issue_key.strip().upper()
    for spec in specs:
        other_key = (spec.issue_key or "").strip().upper()
        if not other_key or other_key == self_key:
            continue
        other_name = to_kebab(spec.proposed_name) if spec.proposed_name else ""
        if other_name and other_name == target:
            return spec
        # Also catch intent.proposed_name when top-level was polluted historically.
        intent_name = (spec.intent or {}).get("proposed_name")
        if intent_name and to_kebab(str(intent_name)) == target:
            return spec
    return None


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
        f"[{spec.issue_key}]({base}/browse/{spec.issue_key})" if base else f"`{spec.issue_key}`"
    )

    summary = (spec.summary or "").strip() or "(none)"
    description = (spec.description or "").strip() or "(no description)"
    if len(description) > _MAX_DESC_CHARS:
        description = description[:_MAX_DESC_CHARS].rstrip() + "\n\n_(truncated)_"

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
        lines.extend(["", "### Eval reasons", *[f"- {r}" for r in spec.evals.reasons]])
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
