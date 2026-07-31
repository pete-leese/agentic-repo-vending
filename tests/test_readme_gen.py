from repo_vendor.readme_gen import build_vended_readme


def test_vended_readme_is_project_not_template():
    text = build_vended_readme(
        repo_name="billing-gateway",
        summary="Billing gateway service",
        description="Handles invoices for EU",
        issue_key="KAN-42",
        template="template-generic-repo",
        repo_url="https://github.com/pete-leese/billing-gateway",
    )
    assert text.startswith("# billing-gateway")
    assert "KAN-42" in text
    assert "Handles invoices" in text
    assert "template-generic-repo" in text
    assert "Python repository template" not in text
    assert "Boilerplate for" not in text
