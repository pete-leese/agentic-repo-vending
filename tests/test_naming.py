from repo_vendor.models import ExtractedIntent, Platform, ProjectType, TerraformShape
from repo_vendor.naming import (
    build_proposed_name,
    infer_intent_from_labels_and_text,
    to_kebab,
    validate_name_and_template,
)


def test_to_kebab_normalizes_snake_and_spaces():
    assert to_kebab("S3_Bucket Module") == "s3-bucket-module"
    assert to_kebab("InvoiceParser") == "invoice-parser"


def test_terraform_module_name():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.MODULE,
        platform=Platform.AWS,
        purpose="s3-bucket",
    )
    assert build_proposed_name(intent) == "terraform-module-s3-bucket-aws"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.template == "template-terraform-repo"


def test_terraform_root_name():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.ROOT,
        purpose="eks-gitops-management",
    )
    assert build_proposed_name(intent) == "terraform-eks-gitops-management"
    assert validate_name_and_template(intent).passed


def test_python_name():
    intent = ExtractedIntent(
        project_type=ProjectType.PYTHON,
        purpose="invoice-parser",
    )
    assert build_proposed_name(intent) == "python-invoice-parser"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.template == "template-python-repo"


def test_generic_name():
    intent = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="billing-gateway",
    )
    assert build_proposed_name(intent) == "billing-gateway"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.template == "template-generic-repo"


def test_default_type_generic_when_unset():
    intent = ExtractedIntent(purpose="docs-site", project_type=None)
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "docs-site"
    assert gate.template == "template-generic-repo"


def test_module_missing_platform_fails():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.MODULE,
        purpose="s3-bucket",
    )
    gate = validate_name_and_template(intent)
    assert not gate.passed


def test_heuristic_extract_from_free_text():
    intent = infer_intent_from_labels_and_text(
        summary="Need terraform module for S3 bucket on AWS",
        description="Please create a reusable module",
        labels=[],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "terraform-module-s3-bucket-aws"
