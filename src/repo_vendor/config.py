from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from repo_vendor.project_config import cfg_keywords, cfg_str, load_project_config


def _yaml_field_map() -> dict[str, Any]:
    """Map repo-vend.yaml into Settings field names."""
    data = load_project_config()
    if not data:
        return {}
    out: dict[str, Any] = {
        "jira_board_url": cfg_str(data, "jira", "board_url"),
        "jira_base_url": cfg_str(data, "jira", "base_url"),
        "jira_new_request_status": cfg_str(
            data, "jira", "statuses", "new_request", default="New Request"
        ),
        "jira_processing_status": cfg_str(
            data, "jira", "statuses", "processing", default="In Progress"
        ),
        "jira_done_status": cfg_str(data, "jira", "statuses", "done", default="Done"),
        "jira_proposed_label": cfg_str(
            data, "jira", "labels", "proposed", default="repo-vend-proposed"
        ),
        "jira_vended_label": cfg_str(data, "jira", "labels", "vended", default="repo-vended"),
        "jira_label_success": cfg_str(
            data, "jira", "labels", "success", default="repo-vend-success"
        ),
        "jira_label_warning": cfg_str(
            data, "jira", "labels", "warning", default="repo-vend-warning"
        ),
        "jira_label_error": cfg_str(data, "jira", "labels", "error", default="repo-vend-error"),
        "approval_keywords": cfg_keywords(data),
        "github_owner": cfg_str(data, "github", "owner", default="pete-leese") or "pete-leese",
        "control_plane_repo": cfg_str(
            data, "github", "control_plane_repo", default="agentic-repo-vending"
        )
        or "agentic-repo-vending",
        "template_terraform": cfg_str(
            data, "github", "templates", "terraform", default="template-terraform-repo"
        )
        or "template-terraform-repo",
        "template_python": cfg_str(
            data, "github", "templates", "python", default="template-python-repo"
        )
        or "template-python-repo",
        "template_generic": cfg_str(
            data, "github", "templates", "generic", default="template-generic-repo"
        )
        or "template-generic-repo",
        "default_project_type": cfg_str(data, "github", "default_project_type", default="generic")
        or "generic",
        "orchestrator_model": cfg_str(data, "models", "orchestrator", default="claude-sonnet-5")
        or "claude-sonnet-5",
        "eval_model": cfg_str(data, "models", "eval", default="composer-2.5") or "composer-2.5",
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


class _YamlSettingsSource(PydanticBaseSettingsSource):
    """Lowest-priority source: repo-vend.yaml (env / init override it)."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        data = _yaml_field_map()
        if field_name in data:
            return data[field_name], field_name, True
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return _yaml_field_map()


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
    control_plane_repo: str = Field(
        default="agentic-repo-vending",
        alias="CONTROL_PLANE_REPO",
        description="Repo that stores requests/*.yaml Spec PRs",
    )
    template_terraform: str = Field(default="template-terraform-repo", alias="TEMPLATE_TERRAFORM")
    template_python: str = Field(default="template-python-repo", alias="TEMPLATE_PYTHON")
    template_generic: str = Field(default="template-generic-repo", alias="TEMPLATE_GENERIC")
    default_project_type: str = Field(default="generic", alias="DEFAULT_PROJECT_TYPE")

    # Jira
    jira_board_url: str = Field(
        default="https://agentic-workflow-demo.atlassian.net/jira/software/projects/REPO/boards/2",
        alias="JIRA_BOARD_URL",
    )
    jira_base_url: str = Field(
        default="https://agentic-workflow-demo.atlassian.net",
        alias="JIRA_BASE_URL",
    )
    jira_new_request_status: str = Field(default="New Request", alias="JIRA_NEW_REQUEST_STATUS")
    jira_vended_label: str = Field(default="repo-vended", alias="JIRA_VENDED_LABEL")
    jira_proposed_label: str = Field(default="repo-vend-proposed", alias="JIRA_PROPOSED_LABEL")
    jira_processing_status: str = Field(default="In Progress", alias="JIRA_PROCESSING_STATUS")
    jira_done_status: str = Field(default="Done", alias="JIRA_DONE_STATUS")
    jira_label_success: str = Field(default="repo-vend-success", alias="JIRA_LABEL_SUCCESS")
    jira_label_warning: str = Field(default="repo-vend-warning", alias="JIRA_LABEL_WARNING")
    jira_label_error: str = Field(default="repo-vend-error", alias="JIRA_LABEL_ERROR")
    approval_keywords: list[str] = Field(
        default_factory=lambda: ["approved", "lgtm", "looks good", "ship it", "+1"],
        alias="APPROVAL_KEYWORDS",
    )

    # Cursor models
    cursor_api_key: str = Field(default="", alias="CURSOR_API_KEY")
    orchestrator_model: str = Field(default="claude-sonnet-5", alias="ORCHESTRATOR_MODEL")
    eval_model: str = Field(default="composer-2.5", alias="EVAL_MODEL")

    # Behaviour
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    allow_llm_fallback: bool = Field(
        default=True,
        alias="ALLOW_LLM_FALLBACK",
        description="If Cursor SDK unavailable, use heuristic extract + rule-only eval.",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority: init kwargs > env > .env > repo-vend.yaml > field defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _YamlSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
