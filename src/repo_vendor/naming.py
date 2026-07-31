"""Deterministic naming and template selection (hard gate).

Human/agent-facing conventions live in ``rules/naming.md`` and ``repo-vend.yaml``.
"""

from __future__ import annotations

import re

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import (
    DeterministicCheckResult,
    ExtractedIntent,
    Platform,
    ProjectType,
    TerraformShape,
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MULTI_DASH = re.compile(r"-{2,}")
_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

TF_MODULE = re.compile(
    r"^terraform-module-(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<platform>aws|gcp|azure)$"
)
TF_ROOT = re.compile(r"^terraform-(?!module-)(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)$")
PYTHON_NAME = re.compile(r"^python-(?P<purpose>[a-z0-9]+(?:-[a-z0-9]+)*)$")
# Generic: plain kebab, not reserved type prefixes
GENERIC_NAME = re.compile(r"^(?!terraform-|python-)[a-z0-9]+(?:-[a-z0-9]+)*$")


def to_kebab(value: str) -> str:
    """Normalize snake_case, spaces, CamelCase fragments into kebab-case."""
    s = value.strip()
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    s = s.replace("_", "-").replace(" ", "-").replace("/", "-")
    s = s.lower()
    s = _NON_ALNUM.sub("-", s)
    s = _MULTI_DASH.sub("-", s).strip("-")
    return s


def is_kebab(value: str) -> bool:
    return bool(_KEBAB.fullmatch(value))


def build_proposed_name(intent: ExtractedIntent) -> str | None:
    """Build canonical name from structured intent when possible."""
    if intent.proposed_name:
        return to_kebab(intent.proposed_name)

    if intent.project_type == ProjectType.PYTHON:
        if not intent.purpose:
            return None
        purpose = to_kebab(intent.purpose)
        if purpose.startswith("python-"):
            return purpose
        return f"python-{purpose}"

    if intent.project_type == ProjectType.TERRAFORM:
        if not intent.purpose:
            return None
        purpose = to_kebab(intent.purpose)
        purpose = re.sub(r"^terraform-(module-)?", "", purpose)
        if intent.terraform_shape == TerraformShape.MODULE:
            if not intent.platform:
                return None
            return f"terraform-module-{purpose}-{intent.platform.value}"
        if intent.terraform_shape == TerraformShape.ROOT:
            return f"terraform-{purpose}"
        return None

    if intent.project_type == ProjectType.GENERIC:
        if not intent.purpose:
            return None
        purpose = to_kebab(intent.purpose)
        for prefix in ("terraform-module-", "terraform-", "python-", "generic-"):
            if purpose.startswith(prefix):
                purpose = purpose[len(prefix) :]
                break
        return purpose or None

    return None


def select_template(project_type: ProjectType, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if project_type == ProjectType.TERRAFORM:
        return settings.template_terraform
    if project_type == ProjectType.PYTHON:
        return settings.template_python
    return settings.template_generic


def _apply_default_type(intent: ExtractedIntent, settings: Settings) -> ExtractedIntent:
    if intent.project_type is not None:
        return intent
    raw = (settings.default_project_type or "generic").lower()
    try:
        intent.project_type = ProjectType(raw)
    except ValueError:
        intent.project_type = ProjectType.GENERIC
    return intent


def validate_name_and_template(
    intent: ExtractedIntent,
    settings: Settings | None = None,
) -> DeterministicCheckResult:
    """Hard gate: kebab + pattern + template mapping."""
    settings = settings or get_settings()
    errors: list[str] = []
    intent = _apply_default_type(intent, settings)

    if intent.project_type is None:
        errors.append(
            "Could not determine project type (terraform, python, or generic). "
            "Add labels type-terraform / type-python / type-generic or clarify "
            "in the description."
        )
        return DeterministicCheckResult(passed=False, errors=errors)

    name = build_proposed_name(intent)
    if not name:
        if intent.project_type == ProjectType.TERRAFORM:
            errors.append(
                "Terraform requests need a purpose slug and shape "
                "(module vs root). Modules also need a platform (aws|gcp|azure). "
                "Example: 'terraform module for S3 bucket on AWS' or label "
                "tf-module + platform-aws."
            )
        elif intent.project_type == ProjectType.PYTHON:
            errors.append(
                "Python requests need a purpose slug. "
                "Example: 'python invoice parser' or propose `python-invoice-parser`."
            )
        else:
            errors.append(
                "Generic requests need a purpose slug. "
                "Example: 'new repo for billing gateway' or propose `billing-gateway`."
            )
        return DeterministicCheckResult(passed=False, errors=errors)

    if not is_kebab(name):
        errors.append(f"Name `{name}` is not valid kebab-case.")

    if intent.project_type == ProjectType.TERRAFORM:
        if intent.terraform_shape == TerraformShape.MODULE or TF_MODULE.fullmatch(name):
            m = TF_MODULE.fullmatch(name)
            if not m:
                errors.append(
                    f"Terraform module names must match "
                    f"`terraform-module-<name>-<platform>`; got `{name}`."
                )
            elif intent.platform and m.group("platform") != intent.platform.value:
                errors.append(
                    f"Platform mismatch: name has `{m.group('platform')}` "
                    f"but intent has `{intent.platform.value}`."
                )
        elif intent.terraform_shape == TerraformShape.ROOT or TF_ROOT.fullmatch(name):
            if not TF_ROOT.fullmatch(name):
                errors.append(
                    f"Terraform root names must match `terraform-<name>` "
                    f"(not terraform-module-...); got `{name}`."
                )
        else:
            errors.append("Specify whether this is a terraform module or root project.")

        if name.startswith("python-"):
            errors.append("Terraform ticket produced a python-prefixed name.")

    if intent.project_type == ProjectType.PYTHON:
        if not PYTHON_NAME.fullmatch(name):
            errors.append(f"Python names must match `python-<purpose-kebab>`; got `{name}`.")
        if name.startswith("terraform-"):
            errors.append("Python ticket produced a terraform-prefixed name.")

    if intent.project_type == ProjectType.GENERIC:
        if not GENERIC_NAME.fullmatch(name):
            errors.append(
                f"Generic names must be kebab-case without `terraform-` / `python-` "
                f"prefixes; got `{name}`."
            )

    if (
        intent.project_type == ProjectType.TERRAFORM
        and intent.terraform_shape == TerraformShape.MODULE
        and intent.platform is None
        and not any("platform" in e.lower() for e in errors)
    ):
        m = TF_MODULE.fullmatch(name)
        if not m:
            errors.append("Terraform modules require platform aws|gcp|azure.")

    template = select_template(intent.project_type, settings)
    passed = len(errors) == 0
    return DeterministicCheckResult(
        passed=passed,
        normalized_name=name if passed else name,
        template=template if passed else None,
        errors=errors,
    )


def infer_intent_from_labels_and_text(
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    """Heuristic fallback when LLM is unavailable (still feeds deterministic gate)."""
    labels_l = {lbl.lower() for lbl in labels}
    blob = f"{summary}\n{description}\n{' '.join(labels)}".lower()

    project_type: ProjectType | None = None
    if "type-terraform" in labels_l or "terraform" in blob:
        project_type = ProjectType.TERRAFORM
    if "type-python" in labels_l or re.search(r"\bpython\b", blob):
        if "type-python" in labels_l:
            project_type = ProjectType.PYTHON
        elif "type-terraform" not in labels_l and "terraform" not in blob:
            project_type = ProjectType.PYTHON
        elif "type-terraform" in labels_l:
            project_type = ProjectType.TERRAFORM
    if "type-generic" in labels_l or re.search(r"\bgeneric\b", blob):
        if "type-generic" in labels_l and "type-terraform" not in labels_l and "type-python" not in labels_l:
            project_type = ProjectType.GENERIC

    shape: TerraformShape | None = None
    if "tf-module" in labels_l or re.search(r"\bmodule\b", blob):
        shape = TerraformShape.MODULE
    if "tf-root" in labels_l or re.search(r"\broot\b", blob) or re.search(r"\bproject\b", blob):
        if "tf-module" not in labels_l and not re.search(r"\bmodule\b", blob):
            shape = TerraformShape.ROOT
        elif "tf-root" in labels_l:
            shape = TerraformShape.ROOT

    platform: Platform | None = None
    for p in Platform:
        if f"platform-{p.value}" in labels_l or re.search(rf"\b{p.value}\b", blob):
            platform = p
            break

    proposed = None
    m = re.search(r"repo\s*name\s*:\s*([a-zA-Z0-9._/\- ]+)", f"{summary}\n{description}", re.I)
    if m:
        proposed = to_kebab(m.group(1))

    purpose = None
    if proposed:
        purpose = proposed
        for prefix in ("terraform-module-", "terraform-", "python-", "generic-"):
            if purpose.startswith(prefix):
                purpose = purpose[len(prefix) :]
                break
        for p in Platform:
            if purpose.endswith(f"-{p.value}"):
                purpose = purpose[: -len(p.value) - 1]
                break
    else:
        purpose_raw = re.sub(
            r"\b(terraform|module|python|generic|repo|repository|new|for|my|on|aws|gcp|azure|"
            r"need|please|create|a|an|the|reusable|project|root)\b",
            " ",
            summary,
            flags=re.I,
        )
        purpose = to_kebab(purpose_raw) or None

    missing: list[str] = []
    # Leave project_type None so validate can apply default_project_type from config
    if project_type == ProjectType.TERRAFORM and shape is None:
        missing.append("terraform shape (module or root)")
    if project_type == ProjectType.TERRAFORM and shape == TerraformShape.MODULE and platform is None:
        missing.append("platform (aws, gcp, or azure)")
    if not purpose and not proposed:
        missing.append("purpose / proposed repo name")

    return ExtractedIntent(
        project_type=project_type,
        terraform_shape=shape,
        platform=platform,
        purpose=purpose,
        proposed_name=proposed,
        confidence=0.4 if not missing else 0.2,
        missing_info=missing,
        notes="heuristic_extract",
    )
