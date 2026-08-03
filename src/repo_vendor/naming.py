"""Deterministic naming and template selection (hard gate).

Machine rules: ``rules/deterministic.yaml`` (patterns, platforms, stopwords, aliases).
Human/HITL prose: ``rules/naming.md``. Project config: ``repo-vend.yaml``.
"""

from __future__ import annotations

import re

from repo_vendor.config import Settings, get_settings
from repo_vendor.deterministic_rules import _LazyPattern, display_for, load_deterministic_rules
from repo_vendor.models import (
    DeterministicCheckResult,
    EvalVerdict,
    ExtractedIntent,
    Platform,
    ProjectType,
    TerraformShape,
)
from repo_vendor.platform_aliases import infer_platform_from_text

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MULTI_DASH = re.compile(r"-{2,}")

# Compiled from rules/deterministic.yaml (lazy so edits reload after cache clear).
TF_MODULE = _LazyPattern("terraform_module")
TF_ROOT = _LazyPattern("terraform_root")
PYTHON_NAME = _LazyPattern("python")
GENERIC_NAME = _LazyPattern("generic")
_KEBAB = _LazyPattern("kebab")


def _purpose_stopwords() -> frozenset[str]:
    return load_deterministic_rules().purpose_stopwords


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


def clean_purpose_slug(value: str | None) -> str | None:
    """Kebab-ize and drop conversational filler tokens from a purpose slug."""
    if not value:
        return None
    stop = _purpose_stopwords()
    parts = [p for p in to_kebab(value).split("-") if p and p not in stop]
    return "-".join(parts) or None


def reconcile_intent_from_proposed_name(intent: ExtractedIntent) -> ExtractedIntent:
    """Align structured fields with a canonical proposed_name when present.

    Typed name patterns (terraform-module-… / terraform-… / python-…) override
    a wrong extract type. Plain kebab forces **generic** so a mistaken
    terraform/python extract cannot rebuild ``terraform-<purpose>`` over a
    judge-corrected generic name (REPO-16).
    """
    name = intent.proposed_name
    if not name:
        return intent
    name = to_kebab(name)
    intent.proposed_name = name

    m = TF_MODULE.fullmatch(name)
    if m:
        intent.project_type = ProjectType.TERRAFORM
        intent.terraform_shape = TerraformShape.MODULE
        if intent.platform is None:
            intent.platform = Platform(m.group("platform"))
        if not intent.purpose:
            intent.purpose = m.group("name")
        return intent

    m = TF_ROOT.fullmatch(name)
    if m:
        intent.project_type = ProjectType.TERRAFORM
        intent.terraform_shape = TerraformShape.ROOT
        if not intent.purpose:
            intent.purpose = m.group("name")
        return intent

    m = PYTHON_NAME.fullmatch(name)
    if m:
        intent.project_type = ProjectType.PYTHON
        intent.terraform_shape = None
        if not intent.purpose:
            intent.purpose = m.group("purpose")
        return intent

    if GENERIC_NAME.fullmatch(name):
        intent.project_type = ProjectType.GENERIC
        intent.terraform_shape = None
        if not intent.purpose:
            intent.purpose = name
        return intent

    return intent


def apply_eval_verdict(
    intent: ExtractedIntent,
    verdict: EvalVerdict,
    settings: Settings | None = None,
) -> ExtractedIntent:
    """Prefer the judge's name/template over a conflicting extract (REPO-16).

    The judge reasons are advisory; its ``proposed_name`` / ``template`` are
    applied before the deterministic gate so the published proposal cannot
    advertise one name while reasons describe another.
    """
    settings = settings or get_settings()
    if verdict.proposed_name:
        intent.proposed_name = to_kebab(verdict.proposed_name)

    tmpl = (verdict.template or "").strip()
    if tmpl:
        if tmpl == settings.template_generic:
            intent.project_type = ProjectType.GENERIC
            intent.terraform_shape = None
        elif tmpl == settings.template_python:
            intent.project_type = ProjectType.PYTHON
            intent.terraform_shape = None
        elif tmpl == settings.template_terraform:
            intent.project_type = ProjectType.TERRAFORM

    return reconcile_intent_from_proposed_name(intent)


def ticket_has_typed_signals(
    *,
    summary: str,
    description: str,
    labels: list[str],
) -> bool:
    """True when the ticket clearly indicates terraform or python (not bare 'project')."""
    labels_l = {lbl.lower() for lbl in labels}
    blob = f"{summary}\n{description}\n{' '.join(labels)}".lower()
    if any(
        lbl.startswith("type-terraform")
        or lbl.startswith("type-python")
        or lbl.startswith("tf-")
        or lbl.startswith("platform-")
        for lbl in labels_l
    ):
        return True
    if "terraform" in blob or re.search(r"\bpython\b", blob):
        return True
    if re.search(r"\bmodule\b", blob) and infer_platform_from_text(blob) is not None:
        return True
    return False


def demote_untyped_weak_intent(
    intent: ExtractedIntent,
    *,
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    """Drop false terraform/python when the ticket has no typed signals.

    Prevents extract/heuristic mistypes (e.g. confidence 0.0 + bare 'project')
    from locking terraform naming before the judge runs.
    """
    if intent.project_type in (None, ProjectType.GENERIC):
        return intent
    if ticket_has_typed_signals(summary=summary, description=description, labels=labels):
        return intent

    intent.project_type = None
    intent.terraform_shape = None
    if intent.proposed_name:
        name = to_kebab(intent.proposed_name)
        m_mod = TF_MODULE.fullmatch(name)
        m_root = TF_ROOT.fullmatch(name)
        m_py = PYTHON_NAME.fullmatch(name)
        if m_mod:
            intent.purpose = intent.purpose or m_mod.group("name")
            intent.proposed_name = None
        elif m_root:
            intent.purpose = intent.purpose or m_root.group("name")
            intent.proposed_name = None
        elif m_py:
            intent.purpose = intent.purpose or m_py.group("purpose")
            intent.proposed_name = None
    return intent


def build_proposed_name(intent: ExtractedIntent) -> str | None:
    """Build canonical name from structured intent when possible.

    Terraform modules always rebuild as ``terraform-module-<purpose>-<platform>``
    so an LLM ``proposed_name`` without a platform suffix cannot drop ``-aws``/etc.
    after platform was derived from S3/EKS/… aliases.

    Purpose prefers a canonical ``proposed_name`` match over a polluted
    ``purpose`` field (e.g. ``give-me-gke`` from "give me a … GKE module").
    """
    if (
        intent.project_type == ProjectType.TERRAFORM
        and intent.terraform_shape == TerraformShape.MODULE
    ):
        purpose = _module_purpose_slug(intent)
        if not purpose or not intent.platform:
            return None
        return f"terraform-module-{purpose}-{intent.platform.value}"

    if intent.project_type == ProjectType.PYTHON:
        if intent.proposed_name:
            name = to_kebab(intent.proposed_name)
            if PYTHON_NAME.fullmatch(name):
                return name
        purpose = clean_purpose_slug(intent.purpose)
        if not purpose:
            return None
        if purpose.startswith("python-"):
            return purpose
        return f"python-{purpose}"

    if intent.project_type == ProjectType.TERRAFORM:
        if intent.proposed_name:
            name = to_kebab(intent.proposed_name)
            if intent.terraform_shape == TerraformShape.ROOT and TF_ROOT.fullmatch(name):
                return name
        purpose = clean_purpose_slug(intent.purpose)
        if not purpose:
            return None
        purpose = re.sub(r"^terraform-(module-)?", "", purpose)
        if intent.terraform_shape == TerraformShape.ROOT:
            return f"terraform-{purpose}"
        return None

    if intent.project_type == ProjectType.GENERIC:
        # Plain kebab only — never keep terraform-/python- prefixes under generic.
        # (If the name was clearly a typed module, enrich_intent_type_and_shape /
        # validate_name_and_template should have coerced type away from generic.)
        raw = clean_purpose_slug(intent.purpose)
        if not raw and intent.proposed_name:
            raw = clean_purpose_slug(intent.proposed_name)
        if not raw:
            return None
        raw = re.sub(r"^terraform-module-", "", raw)
        raw = re.sub(r"^terraform-", "", raw)
        raw = re.sub(r"^python-", "", raw)
        raw = re.sub(r"^generic-", "", raw)
        for p in Platform:
            if raw.endswith(f"-{p.value}"):
                raw = raw[: -len(p.value) - 1]
                break
        return raw or None

    if intent.proposed_name:
        return to_kebab(intent.proposed_name)

    return None


def _module_purpose_slug(intent: ExtractedIntent) -> str | None:
    """Purpose slug for a terraform module, without type/platform prefixes/suffixes.

    Prefer the purpose embedded in a canonical ``proposed_name`` when present so
    conversational filler in ``purpose`` (give-me-…) cannot override a good LLM name.
    """
    if intent.proposed_name:
        name = to_kebab(intent.proposed_name)
        m = TF_MODULE.fullmatch(name)
        if m:
            return m.group("name")

    raw = clean_purpose_slug(intent.purpose)
    if not raw and intent.proposed_name:
        raw = clean_purpose_slug(intent.proposed_name)
    if not raw:
        return None
    raw = re.sub(r"^terraform-(module-)?", "", raw)
    for p in Platform:
        if raw.endswith(f"-{p.value}"):
            raw = raw[: -len(p.value) - 1]
            break
    return clean_purpose_slug(raw)


def enrich_intent_platform(
    intent: ExtractedIntent,
    *,
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    """Fill platform from labels / aws|gcp|azure / service aliases when missing."""
    if intent.platform is not None:
        return intent
    blob = f"{summary}\n{description}\n{' '.join(labels)}"
    inferred = infer_platform_from_text(blob)
    if inferred is None:
        return intent
    intent.platform = inferred
    intent.missing_info = [m for m in intent.missing_info if "platform" not in m.lower()]
    return intent


def enrich_intent_type_and_shape(
    intent: ExtractedIntent,
    *,
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    """Infer terraform/python/module when the ticket omits the word 'terraform'.

    Example: \"I need a EC2 module repo for aws\" → terraform + module + aws.
    Also coerces type from an already-correct proposed_name pattern.
    """
    labels_l = {lbl.lower() for lbl in labels}
    blob = f"{summary}\n{description}\n{' '.join(labels)}".lower()
    has_module = "tf-module" in labels_l or bool(re.search(r"\bmodule\b", blob))
    has_terraform = "type-terraform" in labels_l or "terraform" in blob
    has_python = "type-python" in labels_l or bool(re.search(r"\bpython\b", blob))
    has_cloud = infer_platform_from_text(blob) is not None

    # Coerce from proposed_name patterns first (LLM often names correctly but mistypes)
    proposed = to_kebab(intent.proposed_name) if intent.proposed_name else None
    if proposed and TF_MODULE.fullmatch(proposed):
        intent.project_type = ProjectType.TERRAFORM
        intent.terraform_shape = TerraformShape.MODULE
        m = TF_MODULE.fullmatch(proposed)
        assert m is not None
        if intent.platform is None:
            intent.platform = Platform(m.group("platform"))
        if not intent.purpose:
            intent.purpose = m.group("name")
        intent.missing_info = [
            m_
            for m_ in intent.missing_info
            if "platform" not in m_.lower() and "shape" not in m_.lower()
        ]
        return intent
    if proposed and TF_ROOT.fullmatch(proposed):
        intent.project_type = ProjectType.TERRAFORM
        if intent.terraform_shape is None:
            intent.terraform_shape = TerraformShape.ROOT
        return intent
    if proposed and PYTHON_NAME.fullmatch(proposed):
        intent.project_type = ProjectType.PYTHON
        return intent

    # Infra module language without saying "terraform"
    if intent.project_type in (None, ProjectType.GENERIC) and not has_python:
        if has_terraform or (has_module and has_cloud):
            intent.project_type = ProjectType.TERRAFORM
            intent.missing_info = [
                m_ for m_ in intent.missing_info if "project type" not in m_.lower()
            ]

    if (
        intent.project_type == ProjectType.TERRAFORM
        and intent.terraform_shape is None
        and has_module
    ):
        intent.terraform_shape = TerraformShape.MODULE
        intent.missing_info = [m_ for m_ in intent.missing_info if "shape" not in m_.lower()]

    return intent


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
    # If a typed name is already present, prefer that type over default generic
    if intent.proposed_name:
        enrich_intent_type_and_shape(intent, summary="", description="", labels=[])
    intent = _apply_default_type(intent, settings)

    # Re-coerce if default generic conflicts with a terraform-module-* name
    name_preview = build_proposed_name(intent)
    if (
        intent.project_type == ProjectType.GENERIC
        and name_preview
        and (TF_MODULE.fullmatch(name_preview) or TF_ROOT.fullmatch(name_preview))
    ):
        intent.project_type = ProjectType.TERRAFORM
        if TF_MODULE.fullmatch(name_preview):
            intent.terraform_shape = TerraformShape.MODULE
            m = TF_MODULE.fullmatch(name_preview)
            if m and intent.platform is None:
                intent.platform = Platform(m.group("platform"))
        elif intent.terraform_shape is None:
            intent.terraform_shape = TerraformShape.ROOT

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
                "(module vs root). Modules also need a platform ("
                + "|".join(load_deterministic_rules().platforms)
                + "). "
                "Platform can come from labels (platform-aws), the words aws/gcp/azure, "
                "or a cloud-specific service (see rules/deterministic.yaml aliases). "
                "Example: 'terraform module for EKS' or label tf-module + platform-aws."
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
                    f"`{display_for('terraform_module')}`; got `{name}`."
                )
            elif intent.platform and m.group("platform") != intent.platform.value:
                errors.append(
                    f"Platform mismatch: name has `{m.group('platform')}` "
                    f"but intent has `{intent.platform.value}`."
                )
        elif intent.terraform_shape == TerraformShape.ROOT or TF_ROOT.fullmatch(name):
            if not TF_ROOT.fullmatch(name):
                errors.append(
                    f"Terraform root names must match `{display_for('terraform_root')}` "
                    f"(not terraform-module-...); got `{name}`."
                )
        else:
            errors.append("Specify whether this is a terraform module or root project.")

        if name.startswith("python-"):
            errors.append("Terraform ticket produced a python-prefixed name.")

    if intent.project_type == ProjectType.PYTHON:
        if not PYTHON_NAME.fullmatch(name):
            errors.append(f"Python names must match `{display_for('python')}`; got `{name}`.")
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
            errors.append(
                "Terraform modules require platform "
                + "|".join(load_deterministic_rules().platforms)
                + "."
            )

    template = select_template(intent.project_type, settings)
    passed = len(errors) == 0
    return DeterministicCheckResult(
        passed=passed,
        normalized_name=name if passed else name,
        template=template if passed else None,
        errors=errors,
    )


def enrich_intent_from_heuristics(
    intent: ExtractedIntent,
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    """Fill gaps in LLM extract using label/text heuristics.

    Upgrades generic/unknown project_type when ticket text clearly implies
    terraform or python, unless an explicit ``type-*`` label is present.
    """
    labels_l = {lbl.lower() for lbl in labels}
    heuristic = infer_intent_from_labels_and_text(summary, description, labels)

    explicit_type = any(lbl.startswith("type-") for lbl in labels_l)
    if not explicit_type and intent.project_type in (None, ProjectType.GENERIC):
        if heuristic.project_type and heuristic.project_type != ProjectType.GENERIC:
            intent.project_type = heuristic.project_type

    if intent.terraform_shape is None and heuristic.terraform_shape:
        intent.terraform_shape = heuristic.terraform_shape
    if intent.platform is None and heuristic.platform:
        intent.platform = heuristic.platform
    if not intent.purpose and heuristic.purpose:
        intent.purpose = heuristic.purpose

    return intent


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
    # "EC2 module repo for aws" — infra module without saying terraform
    if (
        project_type is None
        and ("tf-module" in labels_l or re.search(r"\bmodule\b", blob))
        and infer_platform_from_text(blob) is not None
    ):
        project_type = ProjectType.TERRAFORM
    if "type-python" in labels_l or re.search(r"\bpython\b", blob):
        if "type-python" in labels_l:
            project_type = ProjectType.PYTHON
        elif "type-terraform" not in labels_l and "terraform" not in blob and project_type is None:
            project_type = ProjectType.PYTHON
        elif "type-terraform" in labels_l:
            project_type = ProjectType.TERRAFORM
    if "type-generic" in labels_l or re.search(r"\bgeneric\b", blob):
        if (
            "type-generic" in labels_l
            and "type-terraform" not in labels_l
            and "type-python" not in labels_l
        ):
            project_type = ProjectType.GENERIC

    shape: TerraformShape | None = None
    if "tf-module" in labels_l or re.search(r"\bmodule\b", blob):
        shape = TerraformShape.MODULE
    # Do NOT treat bare "project" as terraform root — tickets often say
    # "repo for my project X" with no infra intent (REPO-16).
    if "tf-root" in labels_l or re.search(r"\bterraform\s+root\b", blob):
        shape = TerraformShape.ROOT
    elif re.search(r"\broot\s+(?:project|stack|workspace)\b", blob) and (
        "terraform" in blob or "type-terraform" in labels_l or "tf-module" in labels_l
    ):
        shape = TerraformShape.ROOT
    elif "tf-root" not in labels_l and re.search(r"\broot\b", blob) and "terraform" in blob:
        if "tf-module" not in labels_l and not re.search(r"\bmodule\b", blob):
            shape = TerraformShape.ROOT

    platform = infer_platform_from_text(blob)

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
        purpose = clean_purpose_slug(summary)

    if project_type is None and shape is not None:
        project_type = ProjectType.TERRAFORM

    missing: list[str] = []
    # Leave project_type None so validate can apply default_project_type from config
    if project_type == ProjectType.TERRAFORM and shape is None:
        missing.append("terraform shape (module or root)")
    if (
        project_type == ProjectType.TERRAFORM
        and shape == TerraformShape.MODULE
        and platform is None
    ):
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
