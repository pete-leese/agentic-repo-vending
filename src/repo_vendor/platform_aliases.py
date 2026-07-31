"""Map cloud-specific service names to Platform (aws|gcp|azure).

Used by heuristic extract and documented for LLM extract / judge via rules/naming.md.
"""

from __future__ import annotations

import re

from repo_vendor.models import Platform

# Well-known managed services that imply a single cloud.
# Keys are lowercase tokens matched on word boundaries.
PLATFORM_SERVICE_ALIASES: dict[str, Platform] = {
    # AWS
    "eks": Platform.AWS,
    "ecs": Platform.AWS,
    "ec2": Platform.AWS,
    "s3": Platform.AWS,
    "rds": Platform.AWS,
    "dynamodb": Platform.AWS,
    "lambda": Platform.AWS,
    "sqs": Platform.AWS,
    "sns": Platform.AWS,
    "cloudfront": Platform.AWS,
    "route53": Platform.AWS,
    # GCP
    "gke": Platform.GCP,
    "gcs": Platform.GCP,
    "bigquery": Platform.GCP,
    "cloud-run": Platform.GCP,
    "cloudrun": Platform.GCP,
    "gce": Platform.GCP,
    "pubsub": Platform.GCP,
    # Azure
    "aks": Platform.AZURE,
    "azuread": Platform.AZURE,
    "cosmosdb": Platform.AZURE,
}

_ALIAS_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(PLATFORM_SERVICE_ALIASES, key=len, reverse=True))
    + r")\b",
    re.I,
)


def infer_platform_from_text(blob: str) -> Platform | None:
    """Return platform implied by an explicit cloud name or a known service alias."""
    lower = blob.lower()
    for p in Platform:
        if f"platform-{p.value}" in lower or re.search(rf"\b{p.value}\b", lower):
            return p
    m = _ALIAS_PATTERN.search(lower)
    if not m:
        return None
    return PLATFORM_SERVICE_ALIASES[m.group(1).lower().replace(" ", "-")]
