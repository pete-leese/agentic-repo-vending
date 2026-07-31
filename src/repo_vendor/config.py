from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # GitHub
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_owner: str = Field(default="pete-leese", alias="GITHUB_OWNER")
    template_terraform: str = Field(default="template-terraform-repo", alias="TEMPLATE_TERRAFORM")
    template_python: str = Field(default="template-python-repo", alias="TEMPLATE_PYTHON")

    # Jira label/status *names* for the JSON plan applied by Atlassian Automation tools
    # (CLI does not call Jira; no email/API token required)
    jira_base_url: str = Field(
        default="https://agentic-workflow-demo.atlassian.net",
        alias="JIRA_BASE_URL",
    )
    jira_approved_label: str = Field(default="repo-vend-approved", alias="JIRA_APPROVED_LABEL")
    jira_vended_label: str = Field(default="repo-vended", alias="JIRA_VENDED_LABEL")
    jira_in_review_status: str = Field(default="In Review", alias="JIRA_IN_REVIEW_STATUS")
    jira_processing_status: str = Field(default="In Progress", alias="JIRA_PROCESSING_STATUS")
    jira_done_status: str = Field(default="Done", alias="JIRA_DONE_STATUS")
    jira_label_success: str = Field(default="repo-vend-success", alias="JIRA_LABEL_SUCCESS")
    jira_label_warning: str = Field(default="repo-vend-warning", alias="JIRA_LABEL_WARNING")
    jira_label_error: str = Field(default="repo-vend-error", alias="JIRA_LABEL_ERROR")

    # Cursor models (explicit MVP IDs)
    cursor_api_key: str = Field(default="", alias="CURSOR_API_KEY")
    orchestrator_model: str = Field(default="composer-2.5", alias="ORCHESTRATOR_MODEL")
    eval_model: str = Field(default="composer-2", alias="EVAL_MODEL")

    # Behaviour
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    allow_llm_fallback: bool = Field(
        default=True,
        alias="ALLOW_LLM_FALLBACK",
        description="If Cursor SDK unavailable, use heuristic extract + rule-only eval.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
