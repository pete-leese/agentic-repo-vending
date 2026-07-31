from unittest.mock import MagicMock, patch

from repo_vendor.config import Settings
from repo_vendor.jira_client import JiraClient, JiraIssue
from repo_vendor.workflow import scan_and_vend


def test_search_approved_pending_jql():
    settings = Settings(
        JIRA_PROJECT_KEY="KAN",
        JIRA_IN_REVIEW_STATUS="In Review",
        JIRA_APPROVED_LABEL="repo-vend-approved",
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_EMAIL="a@b.c",
        JIRA_API_TOKEN="x",
    )
    client = JiraClient(settings)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "issues": [
            {
                "key": "KAN-1",
                "fields": {
                    "summary": "Need terraform module for S3 on AWS",
                    "description": None,
                    "status": {"name": "In Review"},
                    "labels": ["repo-vend-approved"],
                },
            }
        ]
    }
    with patch.object(client._client, "get", return_value=mock_response) as get:
        issues = client.search_approved_pending()
    assert len(issues) == 1
    assert issues[0].key == "KAN-1"
    jql = get.call_args.kwargs["params"]["jql"]
    assert 'project = "KAN"' in jql
    assert 'status = "In Review"' in jql
    assert 'labels = "repo-vend-approved"' in jql
    assert 'labels != "repo-vended"' in jql
    client.close()


def test_scan_and_vend_empty():
    settings = Settings(ALLOW_LLM_FALLBACK=True, DRY_RUN=True)
    with patch("repo_vendor.workflow.JiraClient") as jc:
        instance = jc.return_value.__enter__.return_value
        instance.search_approved_pending.return_value = []
        results = scan_and_vend(settings)
    assert results == []


def test_scan_and_vend_calls_vend():
    settings = Settings(ALLOW_LLM_FALLBACK=True, DRY_RUN=True)
    fake = JiraIssue(
        key="KAN-9",
        summary="x",
        description="",
        status="In Review",
        labels=["repo-vend-approved"],
    )
    with patch("repo_vendor.workflow.JiraClient") as jc:
        instance = jc.return_value.__enter__.return_value
        instance.search_approved_pending.return_value = [fake]
        with patch("repo_vendor.workflow.vend_issue") as vend:
            vend.return_value = MagicMock(success=True, issue_key="KAN-9", message="ok")
            results = scan_and_vend(settings, max_issues=5)
    assert len(results) == 1
    vend.assert_called_once_with("KAN-9", settings)
