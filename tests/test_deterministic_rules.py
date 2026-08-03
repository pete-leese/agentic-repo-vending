"""Deterministic rules loaded from rules/deterministic.yaml."""

from __future__ import annotations

from repo_vendor.deterministic_rules import (
    clear_deterministic_rules_cache,
    display_for,
    load_deterministic_rules,
)
from repo_vendor.models import Platform
from repo_vendor.naming import GENERIC_NAME, PYTHON_NAME, TF_MODULE, TF_ROOT, clean_purpose_slug
from repo_vendor.platform_aliases import PLATFORM_SERVICE_ALIASES, infer_platform_from_text
from repo_vendor.prompts import find_repo_root


def test_deterministic_yaml_exists():
    path = find_repo_root() / "rules" / "deterministic.yaml"
    assert path.is_file()


def test_load_compiles_known_patterns():
    clear_deterministic_rules_cache()
    rules = load_deterministic_rules()
    assert rules.platforms == ("aws", "gcp", "azure")
    assert TF_MODULE.fullmatch("terraform-module-s3-bucket-aws")
    assert TF_ROOT.fullmatch("terraform-eks-gitops")
    assert PYTHON_NAME.fullmatch("python-invoice-parser")
    assert GENERIC_NAME.fullmatch("billing-gateway")
    assert not GENERIC_NAME.fullmatch("python-billing")
    assert not TF_MODULE.fullmatch("terraform-module-s3")  # missing platform
    assert display_for("terraform_module") == "terraform-module-<name>-<platform>"


def test_aliases_come_from_yaml():
    clear_deterministic_rules_cache()
    assert PLATFORM_SERVICE_ALIASES["eks"] == Platform.AWS
    assert PLATFORM_SERVICE_ALIASES["gke"] == Platform.GCP
    assert PLATFORM_SERVICE_ALIASES["aks"] == Platform.AZURE
    assert infer_platform_from_text("need an EKS module") == Platform.AWS
    assert infer_platform_from_text("AKS cluster") == Platform.AZURE


def test_purpose_stopwords_from_yaml():
    clear_deterministic_rules_cache()
    assert clean_purpose_slug("give me a repo for GKE") == "gke"
