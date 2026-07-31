from repo_vendor.harness import _coerce_confidence, derive_confidence
from repo_vendor.models import ExtractedIntent, Platform, ProjectType, TerraformShape


def test_coerce_confidence_formats():
    assert _coerce_confidence(None) == 0.0
    assert _coerce_confidence(0.8) == 0.8
    assert _coerce_confidence("0.7") == 0.7
    assert _coerce_confidence("85%") == 0.85
    assert _coerce_confidence(85) == 0.85
    assert _coerce_confidence("high") == 0.85
    assert _coerce_confidence("low") == 0.35


def test_derive_confidence_when_llm_omitted_zero():
    intent = ExtractedIntent(
        project_type=ProjectType.TERRAFORM,
        terraform_shape=TerraformShape.MODULE,
        platform=Platform.AWS,
        purpose="ec2",
        confidence=0.0,
        missing_info=[],
    )
    conf = derive_confidence(intent, gate_passed=True)
    assert conf >= 0.75
    assert conf <= 1.0


def test_derive_confidence_preserves_llm_value():
    intent = ExtractedIntent(
        project_type=ProjectType.PYTHON,
        purpose="logging",
        confidence=0.91,
    )
    assert derive_confidence(intent, gate_passed=True) == 0.91
