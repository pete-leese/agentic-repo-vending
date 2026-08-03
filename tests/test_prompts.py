from repo_vendor.prompts import find_repo_root, format_user_prompt, load_eval, load_rules


def test_find_repo_root_has_evals_and_rules():
    root = find_repo_root()
    assert (root / "evals" / "extract-intent.json").is_file()
    assert (root / "evals" / "judge-naming.json").is_file()
    assert (root / "rules" / "naming.md").is_file()


def test_load_eval_extract_has_system_and_template():
    spec = load_eval("extract-intent")
    assert "system" in spec
    assert "{summary}" in spec["user_template"]
    assert spec["rules_ref"] == "rules/naming.md"


def test_format_judge_injects_naming_rules():
    system, user = format_user_prompt(
        "judge-naming",
        summary="python logging",
        description="helper",
        intent_json='{"project_type":"python"}',
    )
    assert "eval judge" in system.lower() or "Eval judge" in system or "judge" in system.lower()
    assert "python logging" in user
    assert "terraform-module-" in user  # from rules/naming.md
    assert "Keyword Approval" in user or "repo-vend-proposed" in user or "lgtm" in user.lower()
    assert "Cloud documentation context" in user
    assert "(none)" in user


def test_load_eval_extract_has_additional_context_slot():
    spec = load_eval("extract-intent")
    assert "{additional_context}" in spec["user_template"]
    assert "Cloud documentation" in spec["system"] or "documentation context" in spec["system"]


def test_load_rules_mentions_templates():
    text = load_rules()
    assert "template-terraform-repo" in text
    assert "Deterministic gate" in text or "deterministic" in text.lower()
