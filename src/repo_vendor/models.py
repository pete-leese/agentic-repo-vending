from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectType(StrEnum):
    TERRAFORM = "terraform"
    PYTHON = "python"
    GENERIC = "generic"


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
    """LLM eval judge output (model from repo-vend.yaml / EVAL_MODEL)."""

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


class SpecEvals(BaseModel):
    llm_passed: bool
    deterministic_passed: bool
    reasons: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class SpecRequest(BaseModel):
    """Frozen Spec under requests/<ISSUE-KEY>.yaml."""

    issue_key: str
    summary: str = ""
    description: str = ""
    intent: dict[str, Any] = Field(default_factory=dict)
    proposed_name: str
    template: str
    evals: SpecEvals
    status: Literal["proposed", "approved", "vended"] = "proposed"
    pr_url: str | None = None


class PhaseResult(BaseModel):
    """Result of propose or vend (JSON for Automation)."""

    success: bool
    outcome: Literal["success", "warning", "error", "skipped"] = "error"
    phase: Literal["propose", "vend"] = "vend"
    issue_key: str
    repo_name: str | None = None
    repo_url: str | None = None
    template: str | None = None
    proposed_name: str | None = None
    request_path: str | None = None
    pr_url: str | None = None
    message: str
    skipped: bool = False
    jira: JiraUpdatePlan = Field(default_factory=JiraUpdatePlan)
