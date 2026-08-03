"""Cloud documentation context helpers and Spec Description enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from repo_vendor.cloud_docs import (
    format_cloud_notes_section,
    is_terraform_module_spec,
    normalize_additional_context,
    resolve_additional_context,
    ticket_suggests_cloud_docs,
)
from repo_vendor.config import Settings
from repo_vendor.github_client import CreatedRepo, PullRequestInfo
from repo_vendor.models import IssueSnapshot, SpecEvals, SpecRequest
from repo_vendor.prompts import format_user_prompt
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


def _github_mock() -> MagicMock:
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.list_control_plane_specs.return_value = []
    github.repo_exists.return_value = False
    return github


def test_normalize_truncates_and_collapses():
    text = "a\n\n\n\nb" + ("x" * 5000)
    out = normalize_additional_context(text, max_chars=100)
    assert "\n\n\n" not in out
    assert len(out) <= 100
    assert out.endswith("…[truncated]")


def test_ticket_suggests_cloud_docs_for_module_not_generic():
    infra = IssueSnapshot(key="R1", summary="S3 module for aws", labels=["tf-module"])
    generic = IssueSnapshot(key="R2", summary="python logging helper", labels=["type-python"])
    assert ticket_suggests_cloud_docs(infra) is True
    assert ticket_suggests_cloud_docs(generic) is False


def test_format_prompts_include_additional_context():
    _, extract_user = format_user_prompt(
        "extract-intent",
        summary="S3 module",
        description="",
        labels="tf-module",
        additional_context="S3 is an AWS object storage service.",
    )
    assert "Cloud documentation context" in extract_user
    assert "object storage" in extract_user

    _, judge_user = format_user_prompt(
        "judge-naming",
        summary="S3 module",
        description="",
        intent_json='{"platform":"aws"}',
        additional_context="S3 → aws",
    )
    assert "S3 → aws" in judge_user


def test_propose_freezes_additional_context_on_spec():
    settings = _settings()
    digest = "Amazon S3 is object storage. Platform: aws."
    issue = IssueSnapshot(
        key="REPO-CTX",
        summary="terraform module for S3",
        description="bucket module",
        status="New Request",
        labels=["tf-module", "platform-aws"],
        additional_context=digest,
    )
    github = _github_mock()
    github.open_spec_pr.return_value = PullRequestInfo(
        number=99,
        html_url="https://github.com/example/pull/99",
        merged=False,
        state="open",
        head_ref="propose/REPO-CTX",
    )

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = propose_issue(issue, settings=settings)

    assert result.success is True
    yaml_body = github.open_spec_pr.call_args.kwargs["content"]
    assert "additional_context:" in yaml_body
    assert "Amazon S3" in yaml_body


def test_vend_terraform_module_description_includes_cloud_notes():
    settings = _settings()
    issue = IssueSnapshot(key="REPO-TF", labels=["repo-vend-proposed"])
    digest = "AKS is Azure Kubernetes Service. Platform: azure."
    spec = SpecRequest(
        issue_key="REPO-TF",
        summary="terraform module for AKS",
        description="cluster module",
        proposed_name="terraform-module-aks-azure",
        template="template-terraform-repo",
        intent={
            "project_type": "terraform",
            "terraform_shape": "module",
            "platform": "azure",
            "purpose": "aks",
            "proposed_name": "terraform-module-aks-azure",
        },
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
        additional_context=digest,
    )
    assert is_terraform_module_spec(spec) is True
    assert "Cloud documentation notes" in "\n".join(format_cloud_notes_section(digest))

    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.ensure_spec_merged.return_value = None
    github.get_file_text.return_value = spec_to_yaml(spec)
    github.repo_exists.return_value = False
    github.create_from_template.return_value = CreatedRepo(
        name="terraform-module-aks-azure",
        html_url="https://github.com/example/terraform-module-aks-azure",
        full_name="example/terraform-module-aks-azure",
    )
    github.protect_main.return_value = True
    github.wait_for_branch.return_value = True
    github.write_vended_readme.return_value = True

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = vend_issue(issue, approval_comment="lgtm", settings=settings)

    assert result.success is True
    assert result.jira.set_description
    assert "Cloud documentation notes" in result.jira.set_description
    assert "AKS is Azure Kubernetes Service" in result.jira.set_description


def test_vend_python_description_skips_cloud_notes():
    settings = _settings()
    issue = IssueSnapshot(key="REPO-PY", labels=["repo-vend-proposed"])
    spec = SpecRequest(
        issue_key="REPO-PY",
        summary="python helper",
        proposed_name="python-helper",
        template="template-python-repo",
        intent={"project_type": "python", "purpose": "helper"},
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
        additional_context="should not appear for python",
    )
    github = MagicMock()
    github.__enter__.return_value = github
    github.__exit__.return_value = None
    github.ensure_spec_merged.return_value = None
    github.get_file_text.return_value = spec_to_yaml(spec)
    github.repo_exists.return_value = False
    github.create_from_template.return_value = CreatedRepo(
        name="python-helper",
        html_url="https://github.com/example/python-helper",
        full_name="example/python-helper",
    )
    github.protect_main.return_value = True
    github.wait_for_branch.return_value = True
    github.write_vended_readme.return_value = True

    with patch("repo_vendor.workflow.GitHubClient", return_value=github):
        result = vend_issue(issue, approval_comment="approved", settings=settings)

    assert result.success is True
    assert "Cloud documentation notes" not in (result.jira.set_description or "")


def test_resolve_prefers_spec_over_issue():
    issue = IssueSnapshot(key="X", additional_context="from issue")
    spec = SpecRequest(
        issue_key="X",
        proposed_name="terraform-module-s3-aws",
        template="template-terraform-repo",
        evals=SpecEvals(llm_passed=True, deterministic_passed=True),
        additional_context="from spec",
    )
    assert resolve_additional_context(issue, spec=spec) == "from spec"
