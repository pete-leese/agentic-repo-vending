"""PydanticAI typed agents — Cursor harness performs live inference in MVP."""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from repo_vendor.models import EvalVerdict, ExtractedIntent
from repo_vendor.naming import validate_name_and_template

extract_agent = Agent(
    TestModel(),
    output_type=ExtractedIntent,
    system_prompt=(
        "Extract repo vend intent from Jira summary, description, and labels. "
        "Prefer explicit labels when present."
    ),
)


@extract_agent.tool
def run_deterministic_gate(ctx: RunContext[None], intent: ExtractedIntent) -> dict:
    """Expose deterministic naming gate as a PydanticAI tool for agent loops."""
    result = validate_name_and_template(intent)
    return result.model_dump()


eval_agent = Agent(
    TestModel(),
    output_type=EvalVerdict,
    system_prompt=(
        "Judge whether the proposed repo name and template match the request. "
        "Fail closed when information is missing."
    ),
)
