"""PydanticAI typed agents — Cursor harness performs live inference in MVP.

System prompts are loaded from /evals/*.json (same source as harness.py).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from repo_vendor.models import EvalVerdict, ExtractedIntent
from repo_vendor.naming import validate_name_and_template
from repo_vendor.prompts import load_eval

extract_agent = Agent(
    TestModel(),
    output_type=ExtractedIntent,
    system_prompt=str(load_eval("extract-intent")["system"]),
)


@extract_agent.tool
def run_deterministic_gate(ctx: RunContext[None], intent: ExtractedIntent) -> dict:
    """Expose deterministic naming gate as a PydanticAI tool for agent loops."""
    result = validate_name_and_template(intent)
    return result.model_dump()


eval_agent = Agent(
    TestModel(),
    output_type=EvalVerdict,
    system_prompt=str(load_eval("judge-naming")["system"]),
)
