from repo_vendor.models import SpecEvals, SpecRequest
from repo_vendor.spec import format_spec_pr_body, format_spec_pr_title


def _spec(**kwargs) -> SpecRequest:
    base = dict(
        issue_key="REPO-14",
        summary="Need an S3 terraform module for aws",
        description="Create a reusable module for S3 buckets.",
        intent={
            "project_type": "terraform",
            "terraform_shape": "module",
            "platform": "aws",
            "purpose": "s3",
            "confidence": 0.9,
        },
        proposed_name="terraform-module-s3-aws",
        template="template-terraform-repo",
        evals=SpecEvals(
            llm_passed=True,
            deterministic_passed=True,
            reasons=["Matches terraform module naming"],
        ),
    )
    base.update(kwargs)
    return SpecRequest(**base)


def test_format_spec_pr_title():
    assert (
        format_spec_pr_title(_spec())
        == "Propose `terraform-module-s3-aws` (REPO-14)"
    )


def test_format_spec_pr_body_includes_proposal_details():
    body = format_spec_pr_body(
        _spec(),
        jira_base_url="https://agentic-workflow-demo.atlassian.net",
    )
    assert "Propose `terraform-module-s3-aws`" in body
    assert "REPO-14" in body
    assert "/browse/REPO-14" in body
    assert "`template-terraform-repo`" in body
    assert "`aws`" in body
    assert "`module`" in body
    assert "Need an S3 terraform module" in body
    assert "Create a reusable module" in body
    assert "PASSED" in body
    assert "Keyword Approval" in body
    assert "Frozen propose output" not in body


def test_format_spec_pr_body_truncates_long_description():
    long_desc = "x" * 2000
    body = format_spec_pr_body(_spec(description=long_desc))
    assert "_(truncated)_" in body
    assert len(body) < len(long_desc) + 800
