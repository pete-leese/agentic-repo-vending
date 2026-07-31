from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ProjectType(StrEnum):
    TERRAFORM = "terraform"
    PYTHON = "python"


class TerraformShape(StrEnum):
    MODULE = "module"
    ROOT = "root"


class Platform(StrEnum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class ExtractedIntent(BaseModel):
    """Structured intent extracted from a Jira ticket."""

    project_type: ProjectType | None = None
    terraform_shape: TerraformShape | None = None
    platform: Platform | None = None
    purpose: str | None = Field(
        default=None,
        description="Short kebab-friendly purpose slug without type prefixes",
    )
    proposed_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_info: list[str] = Field(default_factory=list)
    notes: str = ""


class EvalVerdict(BaseModel):
    """LLM eval judge output (composer-2)."""

    passed: bool
    proposed_name: str | None = None
    template: str | None = None
    reasons: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class DeterministicCheckResult(BaseModel):
    passed: bool
    normalized_name: str | None = None
    template: str | None = None
    errors: list[str] = Field(default_factory=list)


class IssueSnapshot(BaseModel):
    """Jira issue fields supplied by the Cursor Automation (via Atlassian tools)."""

    key: str
    summary: str = ""
    description: str = ""
    status: str = ""
    labels: list[str] = Field(default_factory=list)


class JiraUpdatePlan(BaseModel):
    """Side-effects for the Automation to apply with Atlassian tools (not REST)."""

    transition_to: str | None = None
    labels_add: list[str] = Field(default_factory=list)
    labels_remove: list[str] = Field(default_factory=list)
    comment_markdown: str = ""


class VendResult(BaseModel):
    success: bool
    outcome: Literal["success", "warning", "error", "skipped"] = "error"
    issue_key: str
    repo_name: str | None = None
    repo_url: str | None = None
    template: str | None = None
    message: str
    skipped: bool = False
    jira: JiraUpdatePlan = Field(default_factory=JiraUpdatePlan)
