"""Regression tests for Bugbot remediations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from repo_vendor.config import Settings
from repo_vendor.github_client import CreatedRepo
from repo_vendor.harness import (
    HeuristicHarness,
    _coerce_bool,
    _coerce_confidence,
    eval_with_harness,
    extract_intent_with_harness,
    get_harness,
)
from repo_vendor.jira_client import JiraIssue
from repo_vendor.models import ExtractedIntent, ProjectType
from repo_vendor.workflow import _success_comment, vend_issue


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("false", False),
        ("False", False),
        ("true", True),
        ("1", True),
        ("0", False),
        ("", False),
        (None, False),
        (0, False),
        (1, True),
    ],
)
def test_coerce_bool(value, expected):
    assert _coerce_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0.0),
        ("", 0.0),
        (0.8, 0.8),
        ("0.5", 0.5),
        ("high", 0.0),
        (1.5, 1.0),
        (-0.2, 0.0),
    ],
)
def test_coerce_confidence(value, expected):
    assert _coerce_confidence(value) == expected


def test_eval_string_false_is_not_pass():
    class FakeHarness(HeuristicHarness):
        name = "llm"

        def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
            return '{"passed": "false", "reasons": ["rejected"], "missing_info": []}'

    verdict = eval_with_harness(
        FakeHarness(),
        model="composer-2",
        intent=ExtractedIntent(project_type=ProjectType.PYTHON, purpose="demo"),
        summary="x",
        description="y",
    )
    assert verdict.passed is False


def test_extract_non_numeric_confidence_does_not_crash():
    class FakeHarness(HeuristicHarness):
        name = "llm"

        def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
            return (
                '{"project_type":"python","purpose":"demo","confidence":"high",'
                '"missing_info":[],"notes":"ok"}'
            )

    intent = extract_intent_with_harness(
        FakeHarness(),
        model="composer-2.5",
        summary="python demo",
        description="demo service",
        labels=["type-python"],
    )
    assert intent.confidence == 0.0
    assert intent.project_type == ProjectType.PYTHON


def test_get_harness_falls_back_when_cursor_sdk_missing():
    settings = Settings(CURSOR_API_KEY="fake-key", ALLOW_LLM_FALLBACK=True)
    with patch(
        "repo_vendor.harness.CursorSdkHarness",
        side_effect=RuntimeError("cursor-sdk is not installed"),
    ):
        h = get_harness(settings)
    assert isinstance(h, HeuristicHarness)


def test_success_comment_reflects_protection_failure():
    ok = _success_comment("python-x", "https://example/x", "template-python-repo")
    assert "direct pushes to `main` are blocked" in ok

    bad = _success_comment(
        "python-x",
        "https://example/x",
        "template-python-repo",
        main_protected=False,
    )
    assert "could not be applied" in bad
    assert "direct pushes to `main` are blocked" not in bad


def test_repo_exists_does_not_apply_vended_label():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_APPROVED_LABEL="repo-vend-approved",
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_IN_REVIEW_STATUS="In Review",
    )
    issue = JiraIssue(
        key="KAN-1",
        summary="python logging helper",
        description="A small python utility for structured logging",
        status="In Review",
        labels=["repo-vend-approved", "type-python"],
    )

    jira = MagicMock()
    jira.__enter__.return_value = jira
    jira.__exit__.return_value = None
    jira.get_issue.return_value = issue
    jira.is_vended.return_value = False
    jira.is_approved.return_value = True

    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.repo_exists.return_value = True

    with (
        patch("repo_vendor.workflow.JiraClient", return_value=jira),
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
        result = vend_issue("KAN-1", settings=settings)

    assert result.success is False
    assert "already exists" in result.message
    # Must not stamp repo-vended on collision; outcome error label is OK.
    vended_adds = [
        c
        for c in jira.add_label.call_args_list
        if c.args and c.args[-1] == "repo-vended"
    ]
    assert vended_adds == []
    assert jira.add_comment.call_count >= 1
    jira.set_outcome_label.assert_called_with("KAN-1", "error")


def test_vend_success_comment_when_protect_fails():
    settings = Settings(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_APPROVED_LABEL="repo-vend-approved",
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_IN_REVIEW_STATUS="In Review",
    )
    issue = JiraIssue(
        key="KAN-2",
        summary="python metrics helper",
        description="A small python utility for metrics",
        status="In Review",
        labels=["repo-vend-approved", "type-python"],
    )

    jira = MagicMock()
    jira.__enter__.return_value = jira
    jira.__exit__.return_value = None
    jira.get_issue.return_value = issue
    jira.is_vended.return_value = False
    jira.is_approved.return_value = True

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
        patch("repo_vendor.workflow.JiraClient", return_value=jira),
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
        result = vend_issue("KAN-2", settings=settings)

    assert result.success is True
    comment = jira.add_comment.call_args_list[-1].args[1]
    assert "could not be applied" in comment
    jira.add_label.assert_any_call("KAN-2", "repo-vended")
    jira.set_outcome_label.assert_called_with("KAN-2", "warning")
    jira.transition_to.assert_any_call("KAN-2", settings.jira_done_status)
