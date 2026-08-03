"""Fetch a short AWS service overview from the public docs search API.

Used as a CLI fallback when the Cloud Agent did not populate
``IssueSnapshot.additional_context``. Fail-open on network errors.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import httpx

from repo_vendor.cloud_docs import cloud_docs_enabled, normalize_additional_context
from repo_vendor.models import IssueSnapshot, Platform
from repo_vendor.platform_aliases import infer_platform_from_text
from repo_vendor.project_config import load_project_config

logger = logging.getLogger(__name__)

SEARCH_API_URL = "https://proxy.search.docs.aws.com/search"
USER_AGENT = (
    "Mozilla/5.0 (compatible; agentic-repo-vending/0.1; "
    "+https://github.com/pete-leese/agentic-repo-vending)"
)

# Friendly product names for "What is …?" queries (purpose slug → query noun).
_SERVICE_QUERY_NAMES: dict[str, str] = {
    "s3": "Amazon S3",
    "ec2": "Amazon EC2",
    "eks": "Amazon EKS",
    "ecs": "Amazon ECS",
    "rds": "Amazon RDS",
    "lambda": "AWS Lambda",
    "dynamodb": "Amazon DynamoDB",
    "sqs": "Amazon SQS",
    "sns": "Amazon SNS",
    "cloudfront": "Amazon CloudFront",
    "route53": "Amazon Route 53",
    "transit-gateway": "AWS Transit Gateway",
    "tgw": "AWS Transit Gateway",
}


def cli_fallback_enabled() -> bool:
    if not cloud_docs_enabled():
        return False
    data = load_project_config()
    section = data.get("cloud_docs") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return True
    return bool(section.get("cli_fallback", True))


def _blob(issue: IssueSnapshot) -> str:
    return " ".join([issue.summary or "", issue.description or "", " ".join(issue.labels or [])])


def infer_aws_service_slug(issue: IssueSnapshot) -> str | None:
    """Best-effort AWS service token from ticket text / aliases."""
    from repo_vendor.deterministic_rules import load_deterministic_rules

    blob = _blob(issue)
    platform = infer_platform_from_text(blob)
    if platform in (Platform.GCP, Platform.AZURE):
        return None

    rules = load_deterministic_rules()
    lower = blob.lower()
    # Prefer longest alias match among AWS services.
    aws_aliases = sorted(
        (k for k, p in rules.service_aliases.items() if p == Platform.AWS),
        key=len,
        reverse=True,
    )
    for alias in aws_aliases:
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return alias.replace(" ", "-")

    # Fallback: token before "terraform module" / "module"
    m = re.search(
        r"\b([a-z0-9]+(?:[-\s][a-z0-9]+)*)\s+(?:terraform\s+)?module\b",
        lower,
    )
    if m:
        return m.group(1).replace(" ", "-")
    return None


def _query_noun(slug: str) -> str:
    if slug in _SERVICE_QUERY_NAMES:
        return _SERVICE_QUERY_NAMES[slug]
    return slug.replace("-", " ").title()


def _parse_suggestions(payload: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in payload.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        sug = item.get("textExcerptSuggestion") or item
        if not isinstance(sug, dict):
            continue
        title = str(sug.get("title") or "").strip()
        summary = str(sug.get("summary") or sug.get("suggestionBody") or "").strip()
        link = str(sug.get("link") or sug.get("url") or "").strip()
        if title or summary:
            out.append({"title": title, "summary": summary, "url": link})
    return out


def search_aws_docs(phrase: str, *, limit: int = 5, timeout: float = 12.0) -> list[dict[str, str]]:
    """POST the public AWS docs search API; return title/summary/url dicts."""
    session = str(uuid.uuid4())
    body = {
        "textQuery": {"input": phrase},
        "contextAttributes": [{"key": "domain", "value": "docs.aws.amazon.com"}],
        "acceptSuggestionBody": "RawText",
        "locales": ["en_us"],
    }
    url = f"{SEARCH_API_URL}?session={session}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "X-MCP-Session-Id": session,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        return []
    return _parse_suggestions(data)[: max(1, limit)]


def format_aws_overview(service_label: str, hits: list[dict[str, str]]) -> str:
    if not hits:
        return ""
    top = hits[0]
    title = top.get("title") or service_label
    # Prefer a clean heading: "What is Amazon Route 53?"
    heading = title.split(" - ")[0].strip() if title else f"What is {service_label}?"
    if not heading.lower().startswith("what is"):
        heading = f"What is {service_label}?"
    lines = [f"### {heading}", ""]
    summary = (top.get("summary") or "").strip()
    if summary:
        lines.append(f"- {summary}")
    lines.append("- Platform: `aws`")
    if top.get("url"):
        lines.append(f"- Docs: {top['url']}")
    # One extra related hit if useful
    if len(hits) > 1 and hits[1].get("summary"):
        extra = hits[1]["summary"].strip()
        if extra and extra != summary:
            lines.append(f"- Related: {extra}")
    return "\n".join(lines).strip()


def maybe_enrich_aws_docs_context(issue: IssueSnapshot) -> str:
    """Return an overview markdown string, or '' if skipped / failed."""
    if not cli_fallback_enabled():
        return ""
    existing = normalize_additional_context(issue.additional_context)
    if existing:
        return ""
    blob = _blob(issue)
    platform = infer_platform_from_text(blob)
    if platform in (Platform.GCP, Platform.AZURE):
        return ""
    if platform is None and not re.search(
        r"\b(aws|terraform|module|tf-module|platform-aws)\b", blob, re.I
    ):
        return ""

    slug = infer_aws_service_slug(issue)
    if not slug:
        return ""
    noun = _query_noun(slug)
    phrase = f"What is {noun}?"
    try:
        hits = search_aws_docs(phrase, limit=3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWS docs CLI fallback failed for %s: %s", phrase, exc)
        return ""
    return normalize_additional_context(format_aws_overview(noun, hits))
