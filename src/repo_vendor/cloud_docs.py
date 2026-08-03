"""Cloud documentation context for propose/evals/vend descriptions.

Cloud Agents enrich IssueSnapshot.additional_context via AWS Docs MCP,
Azure MCP, or future GCP docs MCP (e.g. a \"What is {service}?\" overview).
The CLI never calls those APIs — it feeds the digest into evals, shows it on
the proposal comment, freezes it on the Spec, and (for terraform modules)
surfaces it on the post-vend board Description.
"""

from __future__ import annotations

import re

from repo_vendor.models import IssueSnapshot, SpecRequest
from repo_vendor.platform_aliases import infer_platform_from_text
from repo_vendor.project_config import cfg_str, load_project_config

DEFAULT_MAX_CHARS = 4000

_CLOUD_SIGNAL = re.compile(
    r"\b("
    r"terraform|tf-module|module|"
    r"aws|gcp|azure|platform-aws|platform-gcp|platform-azure|"
    r"eks|ecs|ec2|s3|rds|lambda|dynamodb|sqs|sns|cloudfront|route53|"
    r"transit[\s-]?gateway|tgw|"
    r"gke|gcs|bigquery|cloud[\s-]?run|pubsub|"
    r"aks|cosmos|azure[\s-]?ad"
    r")\b",
    re.IGNORECASE,
)


def cloud_docs_enabled() -> bool:
    data = load_project_config()
    raw = data.get("cloud_docs") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return True
    enabled = raw.get("enabled", True)
    return bool(enabled)


def cloud_docs_max_chars() -> int:
    data = load_project_config()
    raw = cfg_str(data, "cloud_docs", "max_chars", default=str(DEFAULT_MAX_CHARS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_CHARS
    return max(500, min(value, 20_000))


def cloud_docs_mcp_server_names() -> list[str]:
    """Catalog names for Automation prefill (Atlassian always separate)."""
    data = load_project_config()
    section = data.get("cloud_docs") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return []
    providers = section.get("providers")
    if not isinstance(providers, dict):
        return []
    names: list[str] = []
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        if provider.get("enabled") is False:
            continue
        name = provider.get("mcp_server")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def normalize_additional_context(text: str | None, *, max_chars: int | None = None) -> str:
    """Trim, collapse excess blank lines, and cap length for prompts / Spec / Description."""
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    limit = max_chars if max_chars is not None else cloud_docs_max_chars()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 20].rstrip() + "\n…[truncated]"


def ticket_suggests_cloud_docs(issue: IssueSnapshot) -> bool:
    """Heuristic: only enrich infra / terraform / cloud-platform tickets."""
    if not cloud_docs_enabled():
        return False
    blob = " ".join(
        [
            issue.summary or "",
            issue.description or "",
            " ".join(issue.labels or []),
        ]
    )
    if _CLOUD_SIGNAL.search(blob):
        return True
    return infer_platform_from_text(blob) is not None


def resolve_additional_context(
    issue: IssueSnapshot,
    *,
    spec: SpecRequest | None = None,
) -> str:
    """Prefer Spec SoR context at vend; else IssueSnapshot from this run."""
    if spec is not None:
        from_spec = normalize_additional_context(spec.additional_context)
        if from_spec:
            return from_spec
        intent = spec.intent if isinstance(spec.intent, dict) else {}
        legacy = intent.get("additional_context") or intent.get("cloud_docs_context")
        if isinstance(legacy, str):
            from_intent = normalize_additional_context(legacy)
            if from_intent:
                return from_intent
    return normalize_additional_context(issue.additional_context)


def is_terraform_module_spec(spec: SpecRequest) -> bool:
    intent = spec.intent if isinstance(spec.intent, dict) else {}
    shape = intent.get("terraform_shape")
    project_type = intent.get("project_type")
    if project_type == "terraform" and shape == "module":
        return True
    name = (spec.proposed_name or intent.get("proposed_name") or "").strip()
    return name.startswith("terraform-module-")


def format_cloud_notes_section(
    context: str,
    *,
    heading: str = "### Cloud service overview",
) -> list[str]:
    """Markdown lines for proposal comments / post-vend Description."""
    normalized = normalize_additional_context(context)
    if not normalized:
        return []
    return [
        heading,
        "",
        "From cloud documentation MCP (advisory — naming still follows `rules/naming.md`):",
        "",
        normalized,
        "",
    ]
