"""Model harness abstraction — Cursor SDK today; extra harnesses post-MVP."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import EvalVerdict, ExtractedIntent, Platform, ProjectType, TerraformShape

logger = logging.getLogger(__name__)


class ModelHarness(ABC):
    """Swap-out point for Cursor SDK vs future AI harnesses."""

    name: str

    @abstractmethod
    def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
        raise NotImplementedError


class CursorSdkHarness(ModelHarness):
    name = "cursor-sdk"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
        try:
            from cursor_sdk import Agent, LocalAgentOptions
        except ImportError as exc:
            raise RuntimeError(
                "cursor-sdk is not installed. Install with: pip install -e '.[cursor]'"
            ) from exc

        full = prompt if not system else f"{system}\n\n{prompt}"
        with Agent.create(
            model=model,
            api_key=self.api_key,
            local=LocalAgentOptions(cwd="."),
        ) as agent:
            result = agent.send(full)
            # Prefer wait()/text APIs across SDK versions
            if hasattr(result, "wait"):
                waited = result.wait()
                text = getattr(waited, "result", None) or getattr(waited, "text", None)
                if callable(text):
                    return str(text())
                if text:
                    return str(text)
            if hasattr(result, "text"):
                t = result.text
                return str(t() if callable(t) else t)
            # Stream messages fallback
            chunks: list[str] = []
            if hasattr(result, "messages"):
                for message in result.messages():
                    if getattr(message, "type", None) == "assistant":
                        content = getattr(getattr(message, "message", None), "content", []) or []
                        for block in content:
                            if getattr(block, "type", None) == "text":
                                chunks.append(getattr(block, "text", ""))
            return "".join(chunks)


class HeuristicHarness(ModelHarness):
    """No-LLM harness for local tests / missing CURSOR_API_KEY."""

    name = "heuristic"

    def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
        # Tests should not rely on this for structured JSON; callers use naming heuristics.
        return "{}"


def get_harness(settings: Settings | None = None) -> ModelHarness:
    settings = settings or get_settings()
    if settings.cursor_api_key:
        try:
            return CursorSdkHarness(settings.cursor_api_key)
        except Exception:  # noqa: BLE001
            logger.warning("Cursor SDK harness init failed; falling back if allowed")
    if settings.allow_llm_fallback:
        return HeuristicHarness()
    raise RuntimeError("CURSOR_API_KEY required and ALLOW_LLM_FALLBACK is false")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


EXTRACT_SYSTEM = """You extract repo-vend intent from a Jira ticket.
Return ONLY JSON with keys:
project_type: "terraform"|"python"|null
terraform_shape: "module"|"root"|null
platform: "aws"|"gcp"|"azure"|null
purpose: short slug without prefixes
proposed_name: full repo name if stated else null
confidence: 0-1
missing_info: string array
notes: string
"""


EVAL_SYSTEM = """You are an eval judge for repo naming and template selection.
You must NOT invent missing platform/type. Return ONLY JSON:
passed: bool
proposed_name: string|null
template: "template-terraform-repo"|"template-python-repo"|null
reasons: string array
missing_info: string array
Be strict: fail if type/shape/platform/purpose cannot be determined.
"""


def extract_intent_with_harness(
    harness: ModelHarness,
    *,
    model: str,
    summary: str,
    description: str,
    labels: list[str],
) -> ExtractedIntent:
    if harness.name == "heuristic":
        from repo_vendor.naming import infer_intent_from_labels_and_text

        return infer_intent_from_labels_and_text(summary, description, labels)

    prompt = (
        f"Summary: {summary}\n"
        f"Description: {description}\n"
        f"Labels: {', '.join(labels)}\n"
    )
    raw = harness.complete(model=model, prompt=prompt, system=EXTRACT_SYSTEM)
    data = _extract_json(raw)
    return ExtractedIntent(
        project_type=_enum_or_none(ProjectType, data.get("project_type")),
        terraform_shape=_enum_or_none(TerraformShape, data.get("terraform_shape")),
        platform=_enum_or_none(Platform, data.get("platform")),
        purpose=data.get("purpose"),
        proposed_name=data.get("proposed_name"),
        confidence=float(data.get("confidence") or 0),
        missing_info=list(data.get("missing_info") or []),
        notes=str(data.get("notes") or "llm_extract"),
    )


def eval_with_harness(
    harness: ModelHarness,
    *,
    model: str,
    intent: ExtractedIntent,
    summary: str,
    description: str,
) -> EvalVerdict:
    if harness.name == "heuristic":
        # Defer to deterministic gate; soft-pass with built name if intent complete
        from repo_vendor.naming import build_proposed_name, select_template

        name = build_proposed_name(intent)
        if name and intent.project_type and not intent.missing_info:
            return EvalVerdict(
                passed=True,
                proposed_name=name,
                template=select_template(intent.project_type),
                reasons=["heuristic soft-pass; deterministic gate is authoritative"],
            )
        return EvalVerdict(
            passed=False,
            proposed_name=name,
            reasons=["heuristic eval: incomplete intent"],
            missing_info=intent.missing_info
            or ["Insufficient information for naming/template selection"],
        )

    prompt = (
        f"Ticket summary: {summary}\n"
        f"Description: {description}\n"
        f"Extracted intent JSON: {intent.model_dump_json()}\n"
        f"Validate naming conventions: "
        f"terraform-module-<name>-<platform> | terraform-<name> | python-<purpose-kebab>. "
        f"Templates: template-terraform-repo / template-python-repo.\n"
    )
    raw = harness.complete(model=model, prompt=prompt, system=EVAL_SYSTEM)
    data = _extract_json(raw)
    return EvalVerdict(
        passed=bool(data.get("passed")),
        proposed_name=data.get("proposed_name"),
        template=data.get("template"),
        reasons=list(data.get("reasons") or []),
        missing_info=list(data.get("missing_info") or []),
    )


def _enum_or_none(enum_cls: type, value: Any):
    if value is None:
        return None
    try:
        return enum_cls(str(value).lower())
    except ValueError:
        return None
