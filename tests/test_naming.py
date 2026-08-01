from repo_vendor.models import ExtractedIntent, Platform, ProjectType, TerraformShape
from repo_vendor.naming import (
    build_proposed_name,
    enrich_intent_from_heuristics,
    infer_intent_from_labels_and_text,
    reconcile_intent_from_proposed_name,
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


def test_enrich_upgrades_generic_when_text_implies_terraform():
    intent = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="s3",
        proposed_name="terraform-module-s3-aws",
    )
    enriched = enrich_intent_from_heuristics(
        intent,
        summary="i need an s3 terraform module repo",
        description="",
        labels=[],
    )
    assert enriched.project_type == ProjectType.TERRAFORM
    assert enriched.terraform_shape == TerraformShape.MODULE
    assert enriched.platform == Platform.AWS
    gate = validate_name_and_template(enriched)
    assert gate.passed


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


def test_heuristic_s3_module_appends_aws():
    intent = infer_intent_from_labels_and_text(
        summary="i need an s3 terraform module repo",
        description="",
        labels=[],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    assert intent.purpose == "s3"
    assert build_proposed_name(intent) == "terraform-module-s3-aws"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "terraform-module-s3-aws"


def test_module_proposed_name_without_platform_gets_suffix():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.MODULE,
        platform=Platform.AWS,
        purpose="s3",
        proposed_name="terraform-module-s3",  # LLM omitted -aws
    )
    assert build_proposed_name(intent) == "terraform-module-s3-aws"
    assert validate_name_and_template(intent).passed


def test_generic_fallback_plain_kebab_only():
    intent = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="billing-gateway",
    )
    assert build_proposed_name(intent) == "billing-gateway"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.template == "template-generic-repo"
    assert gate.normalized_name == "billing-gateway"


def test_generic_name_builder_strips_typed_prefixes():
    intent = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="terraform-module-billing-aws",
    )
    assert build_proposed_name(intent) == "billing"


def test_heuristic_ec2_module_without_saying_terraform():
    intent = infer_intent_from_labels_and_text(
        summary="I need a EC2 module repo for aws",
        description="",
        labels=[],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    assert build_proposed_name(intent) == "terraform-module-ec2-aws"
    gate = validate_name_and_template(intent)
    assert gate.passed, gate.errors
    assert gate.normalized_name == "terraform-module-ec2-aws"
    assert gate.template == "template-terraform-repo"


def test_module_purpose_ignores_give_me_filler():
    """REPO-15 style: LLM purpose polluted, proposed_name correct."""
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.MODULE,
        platform=Platform.GCP,
        purpose="give-me-gke",
        proposed_name="terraform-module-gke-gcp",
    )
    assert build_proposed_name(intent) == "terraform-module-gke-gcp"
    gate = validate_name_and_template(intent)
    assert gate.passed, gate.errors
    assert gate.normalized_name == "terraform-module-gke-gcp"


def test_heuristic_give_me_gke_module():
    intent = infer_intent_from_labels_and_text(
        summary="give me a repo for a terraform GKE terraform module",
        description="",
        labels=[],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.GCP
    assert intent.purpose == "gke"
    assert build_proposed_name(intent) == "terraform-module-gke-gcp"


def test_generic_mistype_with_terraform_module_proposed_name():
    """LLM named a terraform module but left project_type generic/default."""
    intent = ExtractedIntent(
        project_type=ProjectType.GENERIC,
        purpose="ec2",
        proposed_name="terraform-module-ec2-aws",
        platform=Platform.AWS,
    )
    gate = validate_name_and_template(intent)
    assert gate.passed, gate.errors
    assert gate.normalized_name == "terraform-module-ec2-aws"


def test_heuristic_eks_implies_aws_without_platform_label():
    intent = infer_intent_from_labels_and_text(
        summary="terraform module for EKS cluster networking",
        description="Reusable module",
        labels=["tf-module"],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "terraform-module-eks-cluster-networking-aws"


def test_heuristic_gke_implies_gcp():
    intent = infer_intent_from_labels_and_text(
        summary="Need a terraform module for GKE node pools",
        description="",
        labels=["type-terraform", "tf-module"],
    )
    assert intent.platform == Platform.GCP
    assert validate_name_and_template(intent).passed


def test_heuristic_aks_implies_azure():
    intent = infer_intent_from_labels_and_text(
        summary="terraform module for AKS",
        description="",
        labels=["tf-module"],
    )
    assert intent.platform == Platform.AZURE
    assert validate_name_and_template(intent).passed


def test_heuristic_ec2_module_without_terraform_word():
    intent = infer_intent_from_labels_and_text(
        summary="I need a EC2 module repo for aws",
        description="",
        labels=[],
    )
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "terraform-module-ec2-aws"


def test_reconcile_intent_from_judge_proposed_name():
    intent = ExtractedIntent(proposed_name="terraform-module-ec2-aws")
    intent = reconcile_intent_from_proposed_name(intent)
    assert intent.project_type == ProjectType.TERRAFORM
    assert intent.terraform_shape == TerraformShape.MODULE
    assert intent.platform == Platform.AWS
    assert validate_name_and_template(intent).passed


def test_repo16_project_word_is_not_terraform_root():
    """Bare 'project' must not imply terraform root (REPO-16)."""
    intent = infer_intent_from_labels_and_text(
        summary='give me a repo for my project "invoices-service"',
        description="",
        labels=[],
    )
    assert intent.project_type is None or intent.project_type == ProjectType.GENERIC
    assert intent.terraform_shape is None
    intent.purpose = intent.purpose or "invoices-service"
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "invoices-service"
    assert gate.template == "template-generic-repo"


def test_reconcile_plain_kebab_demotes_false_terraform():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.ROOT,
        purpose="invoices-service",
        proposed_name="invoices-service",
        confidence=0.0,
    )
    intent = reconcile_intent_from_proposed_name(intent)
    assert intent.project_type == ProjectType.GENERIC
    assert intent.terraform_shape is None
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "invoices-service"
    assert gate.template == "template-generic-repo"


def test_apply_eval_verdict_overrides_extract_mistype():
    from repo_vendor.models import EvalVerdict
    from repo_vendor.naming import apply_eval_verdict

    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.ROOT,
        purpose="invoices-service",
        proposed_name="terraform-invoices-service",
        confidence=0.0,
    )
    verdict = EvalVerdict(
        passed=True,
        proposed_name="invoices-service",
        template="template-generic-repo",
        reasons=["unclear → generic"],
    )
    intent = apply_eval_verdict(intent, verdict)
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "invoices-service"
    assert gate.template == "template-generic-repo"


def test_demote_untyped_weak_intent_clears_false_terraform():
    from repo_vendor.naming import demote_untyped_weak_intent

    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.ROOT,
        purpose="invoices-service",
        confidence=0.0,
    )
    intent = demote_untyped_weak_intent(
        intent,
        summary='give me a repo for my project "invoices-service"',
        description="",
        labels=[],
    )
    assert intent.project_type is None
    assert intent.terraform_shape is None
    gate = validate_name_and_template(intent)
    assert gate.passed
    assert gate.normalized_name == "invoices-service"
