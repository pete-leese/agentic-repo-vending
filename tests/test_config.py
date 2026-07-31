from repo_vendor.config import Settings, get_settings
from repo_vendor.project_config import load_project_config, project_config_path


def test_repo_vend_yaml_loads():
    load_project_config.cache_clear()
    data = load_project_config()
    assert data["jira"]["board_url"]
    assert "lgtm" in data["jira"]["approval"]["keywords"]
    assert data["github"]["templates"]["generic"] == "template-generic-repo"
    assert project_config_path() is not None


def test_settings_pick_up_yaml_templates():
    get_settings.cache_clear()
    load_project_config.cache_clear()
    s = get_settings()
    assert s.template_generic == "template-generic-repo"
    assert s.jira_board_url.startswith("https://")
    assert "approved" in s.approval_keywords


def test_settings_init_overrides_yaml():
    s = Settings(TEMPLATE_GENERIC="my-generic-template", APPROVAL_KEYWORDS=["ship it"])
    assert s.template_generic == "my-generic-template"
    assert s.approval_keywords == ["ship it"]
