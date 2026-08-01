from unittest.mock import MagicMock, patch

from repo_vendor.config import Settings
from repo_vendor.github_client import CreatedRepo, PullRequestInfo
from repo_vendor.models import IssueSnapshot, SpecEvals, SpecRequest
from repo_vendor.spec import spec_to_yaml
from repo_vendor.workflow import propose_issue, vend_issue


def _settings(**kwargs) -> Settings:
    base = dict(
        CURSOR_API_KEY="",
        ALLOW_LLM_FALLBACK=True,
        JIRA_VENDED_LABEL="repo-vended",
        JIRA_PROPOSED_LABEL="repo-vend-proposed",
    )
    base.update(kwargs)
    return Settings(**base)


def test_propose_eval_fail_no_pr():
    settings = _settings()
    issue = IssueSnapshot(
        key="KAN-9",
        summary="Need a repo",
        description="something vague",
        status="New Request",
        labels=[],
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = propose_issue(issue, settings=settings)

    assert result.success is False
    assert result.phase == "propose"
    assert result.outcome == "error"
    github.open_spec_pr.assert_not_called()
    assert settings.jira_label_error in result.jira.labels_add


def test_propose_pass_opens_spec_pr():
    settings = _settings()
    issue = IssueSnapshot(
        key="KAN-10",
        summary="python logging helper",
        description="A small python utility for structured logging",
        status="New Request",
        labels=["type-python"],
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.open_spec_pr.return_value = PullRequestInfo(
        number=3,
        html_url="https://github.com/pete-leese/agentic-repo-vending/pull/3",
        merged=False,
        state="open",
        head_ref="propose/KAN-10",
    )

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = propose_issue(issue, settings=settings)

    assert result.success is True
    assert result.phase == "propose"
    assert result.proposed_name
    assert result.proposed_name.startswith("python-")
    github.open_spec_pr.assert_called_once()
    pr_kwargs = github.open_spec_pr.call_args.kwargs
    assert result.proposed_name in pr_kwargs["title"]
    assert "KAN-10" in pr_kwargs["title"]
    assert result.proposed_name in pr_kwargs["body"]
    assert "template-python-repo" in pr_kwargs["body"]
    assert "Keyword Approval" in pr_kwargs["body"]
    assert "Frozen propose output" not in pr_kwargs["body"]
    assert "repo-vend-proposed" in result.jira.labels_add
    assert settings.jira_label_error in result.jira.labels_remove
    assert "PASSED" in result.jira.comment_markdown
    assert "lgtm" in result.jira.comment_markdown.lower()
    assert "**Confidence:**" in result.jira.comment_markdown
    assert result.confidence is not None and result.confidence > 0
    # Spec YAML intent.confidence must not stay at the 0.0 default
    yaml_body = pr_kwargs["content"]
    assert "confidence: 0.0" not in yaml_body
    assert "confidence:" in yaml_body


def test_propose_pass_includes_cursor_agent_link():
    settings = _settings()
    issue = IssueSnapshot(
        key="KAN-10b",
        summary="python logging helper",
        description="A small python utility for structured logging",
        status="New Request",
        labels=["type-python"],
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.open_spec_pr.return_value = PullRequestInfo(
        number=4,
        html_url="https://github.com/pete-leese/agentic-repo-vending/pull/4",
        merged=False,
        state="open",
        head_ref="propose/KAN-10b",
    )
    agent = "bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = propose_issue(
            issue, settings=settings, cursor_agent_id=agent
        )

    assert result.success is True
    assert result.cursor_agent_id == agent
    assert f"https://cursor.com/agents/{agent}" in result.jira.comment_markdown
    assert "**Confidence:**" in result.jira.comment_markdown


def test_vend_uses_intent_proposed_name_when_top_level_polluted():
    settings = _settings()
    issue = IssueSnapshot(
        key="REPO-15",
        summary="give me a repo for a terraform GKE terraform module",
        labels=["repo-vend-proposed"],
    )
    spec = SpecRequest(
        issue_key="REPO-15",
        summary="give me a repo for a terraform GKE terraform module",
        proposed_name="terraform-module-give-me-gke-gcp",
        template="template-terraform-repo",
        intent={
            "project_type": "terraform",
            "terraform_shape": "module",
            "platform": "gcp",
            "purpose": "give-me-gke",
            "proposed_name": "terraform-module-gke-gcp",
        },
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.ensure_spec_merged.return_value = None
    github.get_file_text.return_value = spec_to_yaml(spec)
    github.repo_exists.return_value = False
    github.create_from_template.return_value = CreatedRepo(
        name="terraform-module-gke-gcp",
        html_url="https://github.com/example/terraform-module-gke-gcp",
        full_name="example/terraform-module-gke-gcp",
    )
    github.protect_main.return_value = True
    github.write_vended_readme.return_value = True

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = vend_issue(issue, approval_comment="lgtm", settings=settings)

    assert result.success is True
    assert result.repo_name == "terraform-module-gke-gcp"
    github.create_from_template.assert_called_once()
    assert github.create_from_template.call_args.kwargs["name"] == "terraform-module-gke-gcp"


def test_vend_from_spec_success_warning_on_protect():
    settings = _settings()
    issue = IssueSnapshot(
        key="KAN-12",
        summary="python metrics helper",
        labels=["repo-vend-proposed"],
    )
    spec = SpecRequest(
        issue_key="KAN-12",
        summary="python metrics helper",
        description="metrics",
        proposed_name="python-metrics-helper",
        template="template-python-repo",
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
        status="proposed",
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.ensure_spec_merged.return_value = None
    github.get_file_text.return_value = spec_to_yaml(spec)
    github.repo_exists.return_value = False
    github.create_from_template.return_value = CreatedRepo(
        name="python-metrics-helper",
        html_url="https://github.com/example/python-metrics-helper",
        full_name="example/python-metrics-helper",
    )
    github.protect_main.return_value = False
    github.write_vended_readme.return_value = True

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = vend_issue(issue, approval_comment="lgtm", settings=settings)

    assert result.success is True
    assert result.outcome == "warning"
    github.write_vended_readme.assert_called_once()
    assert "repo-vended" in result.jira.labels_add
    assert settings.jira_label_warning in result.jira.labels_add
    assert result.jira.transition_to == settings.jira_done_status
    assert result.jira.set_description
    assert "python-metrics-helper" in result.jira.set_description
    assert "Approved repo vend" in result.jira.set_description


def test_vend_repo_exists_no_vended_label():
    settings = _settings()
    issue = IssueSnapshot(key="KAN-13", labels=["repo-vend-proposed"])
    spec = SpecRequest(
        issue_key="KAN-13",
        proposed_name="python-logging-helper",
        template="template-python-repo",
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.ensure_spec_merged.return_value = None
    github.get_file_text.return_value = spec_to_yaml(spec)
    github.repo_exists.return_value = True

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = vend_issue(issue, approval_comment="approved", settings=settings)

    assert result.success is False
    assert settings.jira_vended_label not in result.jira.labels_add
    assert settings.jira_label_error in result.jira.labels_add
