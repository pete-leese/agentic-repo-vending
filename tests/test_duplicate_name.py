"""Duplicate proposed-name detection against Spec Requests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from repo_vendor.config import Settings
from repo_vendor.github_client import PullRequestInfo
from repo_vendor.models import (
    EvalVerdict,
    ExtractedIntent,
    IssueSnapshot,
    ProjectType,
    SpecEvals,
    SpecRequest,
)
from repo_vendor.spec import (
    find_duplicate_proposed_name,
    load_specs_from_requests_dir,
    spec_to_yaml,
)
from repo_vendor.workflow import propose_issue


def _spec(issue_key: str, name: str) -> SpecRequest:
    return SpecRequest(
        issue_key=issue_key,
        proposed_name=name,
        template="template-generic-repo",
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
    )


def test_find_duplicate_ignores_same_issue():
    specs = [_spec("REPO-16", "invoices-service")]
    assert (
        find_duplicate_proposed_name("invoices-service", issue_key="REPO-16", specs=specs) is None
    )


def test_find_duplicate_detects_other_issue():
    specs = [
        _spec("REPO-14", "terraform-module-s3-bucket-aws"),
        _spec("REPO-16", "invoices-service"),
    ]
    hit = find_duplicate_proposed_name("invoices-service", issue_key="REPO-99", specs=specs)
    assert hit is not None
    assert hit.issue_key == "REPO-16"


def test_find_duplicate_normalizes_kebab():
    specs = [_spec("REPO-1", "Billing-Gateway")]
    hit = find_duplicate_proposed_name("billing_gateway", issue_key="REPO-2", specs=specs)
    assert hit is not None
    assert hit.issue_key == "REPO-1"


def test_load_specs_from_requests_dir(tmp_path: Path):
    req = tmp_path / "requests"
    req.mkdir()
    (req / "REPO-A.yaml").write_text(
        spec_to_yaml(_spec("REPO-A", "alpha-service")), encoding="utf-8"
    )
    (req / "REPO-B.yaml").write_text(
        spec_to_yaml(_spec("REPO-B", "beta-service")), encoding="utf-8"
    )
    (req / "README.md").write_text("docs", encoding="utf-8")
    specs = load_specs_from_requests_dir(tmp_path)
    names = {s.issue_key: s.proposed_name for s in specs}
    assert names == {"REPO-A": "alpha-service", "REPO-B": "beta-service"}


def test_propose_fails_on_duplicate_spec_name():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_PROPOSED_LABEL="repo-vend-proposed",
    )
    issue = IssueSnapshot(
        key="REPO-99",
        summary='give me a repo for my project "invoices-service"',
        description="",
        status="New Request",
        labels=[],
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.list_control_plane_specs.return_value = [
        _spec("REPO-16", "invoices-service"),
    ]
    github.repo_exists.return_value = False

    extract = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="invoices-service",
        proposed_name="invoices-service",
        confidence=0.9,
    )
    verdict = EvalVerdict(
        passed=True,
        proposed_name="invoices-service",
        template="template-generic-repo",
        reasons=["generic"],
    )

    with (
        patch("repo_vendor.workflow.GitHubClient", return_value=github),
        patch("repo_vendor.workflow.extract_intent_with_harness", return_value=extract),
        patch("repo_vendor.workflow.eval_with_harness", return_value=verdict),
    ):
        result = propose_issue(issue, settings=settings)

    assert result.success is False
    assert result.outcome == "error"
    assert "duplicate name" in result.message.lower()
    assert "REPO-16" in result.message
    assert "invoices-service" in result.message
    assert settings.jira_label_error in result.jira.labels_add
    github.open_spec_pr.assert_not_called()


def test_propose_allows_repropose_same_issue_same_name():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_PROPOSED_LABEL="repo-vend-proposed",
    )
    issue = IssueSnapshot(
        key="REPO-16",
        summary='give me a repo for my project "invoices-service"',
        status="New Request",
        labels=["repo-vend-proposed"],
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.list_control_plane_specs.return_value = [
        _spec("REPO-16", "invoices-service"),
    ]
    github.repo_exists.return_value = False
    github.open_spec_pr.return_value = PullRequestInfo(
        number=30,
        html_url="https://github.com/example/pull/30",
        merged=False,
        state="open",
        head_ref="propose/REPO-16",
    )

    extract = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="invoices-service",
        proposed_name="invoices-service",
        confidence=0.9,
    )
    verdict = EvalVerdict(
        passed=True,
        proposed_name="invoices-service",
        template="template-generic-repo",
        reasons=["generic"],
    )

    with (
        patch("repo_vendor.workflow.GitHubClient", return_value=github),
        patch("repo_vendor.workflow.extract_intent_with_harness", return_value=extract),
        patch("repo_vendor.workflow.eval_with_harness", return_value=verdict),
    ):
        result = propose_issue(issue, settings=settings)

    assert result.success is True
    assert result.proposed_name == "invoices-service"
    github.open_spec_pr.assert_called_once()
