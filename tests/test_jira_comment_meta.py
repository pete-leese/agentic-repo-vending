from repo_vendor.cursor_run import (
    format_cursor_agent_line,
    normalize_cursor_agent_id,
    resolve_cursor_agent,
)
from repo_vendor.workflow import _failure_markdown, _proposal_markdown, _success_markdown


def test_normalize_and_resolve_agent():
    assert normalize_cursor_agent_id("bc-11111111-2222-3333-4444-555555555555")
    assert (
        normalize_cursor_agent_id("11111111-2222-3333-4444-555555555555")
        == "bc-11111111-2222-3333-4444-555555555555"
    )
    assert normalize_cursor_agent_id("not-an-id") is None
    aid, url = resolve_cursor_agent(
        agent_id="bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    assert aid.startswith("bc-")
    assert url == f"https://cursor.com/agents/{aid}"
    aid2, _ = resolve_cursor_agent(
        env={"CURSOR_CLOUD_AGENT_ID": "bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    )
    assert aid2 == "bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_proposal_comment_includes_confidence_and_agent_link():
    md = _proposal_markdown(
        issue_key="REPO-14",
        proposed_name="python-logging-helper",
        template="template-python-repo",
        llm_passed=True,
        deterministic_passed=True,
        reasons=[],
        missing=[],
        pr_url="https://github.com/example/pull/1",
        confidence=0.86,
        cursor_agent_id="bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        cursor_agent_url="https://cursor.com/agents/bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert "**Confidence:** `0.86`" in md
    assert "Cursor agent" in md
    assert "https://cursor.com/agents/bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in md
    assert format_cursor_agent_line(
        agent_id="bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ) in md


def test_failure_and_success_comments_include_agent():
    fail = _failure_markdown(
        ["vague"],
        [],
        confidence=0.4,
        cursor_agent_id="bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        cursor_agent_url="https://cursor.com/agents/bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert "**Confidence:** `0.40`" in fail
    assert "cursor.com/agents/" in fail
    ok = _success_markdown(
        "python-logging-helper",
        "https://github.com/example/python-logging-helper",
        "template-python-repo",
        main_protected=True,
        cursor_agent_id="bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        cursor_agent_url="https://cursor.com/agents/bc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert "cursor.com/agents/" in ok
