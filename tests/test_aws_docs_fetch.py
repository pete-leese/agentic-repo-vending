"""CLI AWS docs fallback for proposal cloud-service overviews."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from repo_vendor.aws_docs_fetch import (
    format_aws_overview,
    infer_aws_service_slug,
    maybe_enrich_aws_docs_context,
)
from repo_vendor.config import Settings
from repo_vendor.github_client import PullRequestInfo
from repo_vendor.models import IssueSnapshot
from repo_vendor.workflow import propose_issue


def test_infer_route53_slug():
    issue = IssueSnapshot(
        key="R",
        summary="create me a repo for route53 terraform module",
    )
    assert infer_aws_service_slug(issue) == "route53"


def test_format_aws_overview():
    text = format_aws_overview(
        "Amazon Route 53",
        [
            {
                "title": "What is Amazon Route 53? - Amazon Route 53",
                "summary": "Register domains and route internet traffic.",
                "url": "https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Welcome.html",
            }
        ],
    )
    assert "### What is Amazon Route 53?" in text
    assert "Register domains" in text
    assert "Platform: `aws`" in text
    assert "docs.aws.amazon.com" in text


def test_maybe_enrich_skips_when_context_present():
    issue = IssueSnapshot(
        key="R",
        summary="route53 terraform module",
        additional_context="### already set",
    )
    assert maybe_enrich_aws_docs_context(issue) == ""


def test_propose_cli_fallback_adds_overview_to_comment():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_PROPOSED_LABEL="repo-vend-proposed",
    )
    issue = IssueSnapshot(
        key="REPO-FB",
        summary="create me a repo for route53 terraform module",
        status="New Request",
        labels=[],
        additional_context="",  # Automation skipped MCP
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.list_control_plane_specs.return_value = []
    github.repo_exists.return_value = False
    github.open_spec_pr.return_value = PullRequestInfo(
        number=1,
        html_url="https://github.com/example/pull/1",
        merged=False,
        state="open",
        head_ref="propose/REPO-FB",
    )
    overview = (
        "### What is Amazon Route 53?\n"
        "- Register domains and route traffic.\n"
        "- Platform: `aws`\n"
        "- Docs: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Welcome.html"
    )

    with (
        patch("repo_vendor.workflow.GitHubClient", return_value=github),
        patch(
            "repo_vendor.workflow.maybe_enrich_aws_docs_context",
            return_value=overview,
        ),
    ):
        result = propose_issue(issue, settings=settings)

    assert result.success is True
    assert "Cloud service overview" in result.jira.comment_markdown
    assert "What is Amazon Route 53?" in result.jira.comment_markdown
    assert "Amazon Route 53" in github.open_spec_pr.call_args.kwargs["content"]
