from unittest.mock import MagicMock, patch

from repo_vendor.config import Settings
from repo_vendor.github_client import CreatedRepo
from repo_vendor.models import IssueSnapshot
from repo_vendor.workflow import vend_issue


def test_repo_exists_does_not_apply_vended_label():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_APPROVED_LABEL="repo-vend-approved",
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_IN_REVIEW_STATUS="In Review",
    )
    issue = IssueSnapshot(
        key="KAN-1",
        summary="python logging helper",
        description="A small python utility for structured logging",
        status="In Review",
        labels=["repo-vend-approved", "type-python"],
    )

    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.repo_exists.return_value = True

    with (
        patch("repo_vendor.workflow.GitHubClient", return_value=github),
        patch(
            "repo_vendor.workflow.validate_name_and_template",
            return_value=MagicMock(
                passed=True,
                normalized_name="python-logging-helper",
                template="template-python-repo",
                errors=[],
            ),
        ),
    ):
        result = vend_issue(issue, settings=settings)

    assert result.success is False
    assert result.outcome == "error"
    assert "already exists" in result.message
    assert settings.jira_vended_label not in result.jira.labels_add
    assert settings.jira_label_error in result.jira.labels_add


def test_vend_success_comment_when_protect_fails():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_APPROVED_LABEL="repo-vend-approved",
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_IN_REVIEW_STATUS="In Review",
    )
    issue = IssueSnapshot(
        key="KAN-2",
        summary="python metrics helper",
        description="A small python utility for metrics",
        status="In Review",
        labels=["repo-vend-approved", "type-python"],
    )

    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.repo_exists.return_value = False
    github.create_from_template.return_value = CreatedRepo(
        name="python-metrics-helper",
        html_url="https://github.com/example/python-metrics-helper",
        full_name="example/python-metrics-helper",
    )
    github.protect_main.return_value = False

    with (
        patch("repo_vendor.workflow.GitHubClient", return_value=github),
        patch(
            "repo_vendor.workflow.validate_name_and_template",
            return_value=MagicMock(
                passed=True,
                normalized_name="python-metrics-helper",
                template="template-python-repo",
                errors=[],
            ),
        ),
    ):
        result = vend_issue(issue, settings=settings)

    assert result.success is True
    assert result.outcome == "warning"
    assert "could **not** be applied" in result.jira.comment_markdown or (
        "could not be applied" in result.jira.comment_markdown
    )
    assert "repo-vended" in result.jira.labels_add
    assert settings.jira_label_warning in result.jira.labels_add
    assert result.jira.transition_to == settings.jira_done_status
    assert "https://github.com/example/python-metrics-helper" in result.jira.comment_markdown
