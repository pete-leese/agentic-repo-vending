"""Model harness abstraction — Cursor SDK today; extra harnesses post-MVP."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from repo_vendor.config import Settings, get_settings
from repo_vendor.models import EvalVerdict, ExtractedIntent, Platform, ProjectType, TerraformShape
from repo_vendor.prompts import format_user_prompt

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
        # Import eagerly so get_harness can fall back when the extra is missing.
        try:
            from cursor_sdk import Agent, LocalAgentOptions  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "cursor-sdk is not installed. Install with: pip install -e '.[cursor]'"
            ) from exc
        self.api_key = api_key

    def complete(self, *, model: str, prompt: str, system: str | None = None) -> str:
        from cursor_sdk import Agent, LocalAgentOptions

        full = prompt if not system else f"{system}\n\n{prompt}"
        with Agent.create(
            model=model,
            api_key=self.api_key,
            local=LocalAgentOptions(cwd="."),
        ) as agent:
            result = agent.send(full)
            waited: Any = None
            # Prefer wait()/text APIs across SDK versions
            if hasattr(result, "wait"):
                waited = result.wait()
                text = getattr(waited, "result", None) or getattr(waited, "text", None)
                if callable(text):
                    out = str(text())
                elif text:
                    out = str(text)
                else:
                    out = ""
            elif hasattr(result, "text"):
                t = result.text
                out = str(t() if callable(t) else t)
            else:
                # Stream messages fallback
                chunks: list[str] = []
                if hasattr(result, "messages"):
                    for message in result.messages():
                        if getattr(message, "type", None) == "assistant":
                            content = (
                                getattr(getattr(message, "message", None), "content", []) or []
                            )
                            for block in content:
                                if getattr(block, "type", None) == "text":
                                    chunks.append(getattr(block, "text", ""))
                out = "".join(chunks)

            _record_run_tokens(
                model=model,
                waited=waited if waited is not None else result,
                agent=agent,
                prompt=full,
                response=out,
            )
            return out


def _record_run_tokens(
    *,
    model: str,
    waited: Any,
    agent: Any = None,
    prompt: str = "",
    response: str = "",
) -> None:
    """Best-effort token metrics from RunResult.usage, get_usage(), or char estimate."""
    try:
        from repo_vendor.observability import MetricEvent, get_metrics_sink

        sink = get_metrics_sink()
        usage = getattr(waited, "usage", None)

        # Local agents often leave RunResult.usage empty; try billed GetUsage.
        if usage is None and agent is not None and hasattr(agent, "get_usage"):
            try:
                run_id = getattr(waited, "id", None) or getattr(waited, "run_id", None)
                agent_usage = agent.get_usage(run_id=run_id) if run_id else agent.get_usage()
                usage = getattr(agent_usage, "usage", None) or agent_usage
            except Exception:  # noqa: BLE001
                logger.debug("agent.get_usage unavailable", exc_info=True)

        input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage is not None else 0
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage is not None else 0
        if input_tokens or output_tokens:
            sink.record_tokens(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
            return

        total = int(getattr(usage, "total_tokens", 0) or 0) if usage is not None else 0
        if total:
            sink.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=float(total),
                    attributes={"model": model, "direction": "total"},
                )
            )
            return

        # Fallback so the tokens panel is not empty when SDK omits usage.
        if prompt or response:
            est_in = max(1, len(prompt) // 4) if prompt else 0
            est_out = max(1, len(response) // 4) if response else 0
            if est_in:
                sink.emit(
                    MetricEvent(
                        name="llm.tokens",
                        value=float(est_in),
                        attributes={"model": model, "direction": "estimate_input"},
                    )
                )
            if est_out:
                sink.emit(
                    MetricEvent(
                        name="llm.tokens",
                        value=float(est_out),
                        attributes={"model": model, "direction": "estimate_output"},
                    )
                )
    except Exception:  # noqa: BLE001 — never fail propose/vend on metrics
        logger.debug("token usage metrics skipped", exc_info=True)


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
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Cursor SDK harness init failed (%s); falling back if allowed",
                exc,
            )
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


def extract_intent_with_harness(
    harness: ModelHarness,
    *,
    model: str,
    summary: str,
    description: str,
    labels: list[str],
    additional_context: str = "",
) -> ExtractedIntent:
    if harness.name == "heuristic":
        from repo_vendor.naming import infer_intent_from_labels_and_text

        return infer_intent_from_labels_and_text(summary, description, labels)

    from repo_vendor.cloud_docs import normalize_additional_context

    ctx = normalize_additional_context(additional_context) or "(none)"
    system, prompt = format_user_prompt(
        "extract-intent",
        summary=summary,
        description=description,
        labels=", ".join(labels),
        additional_context=ctx,
    )
    raw = harness.complete(model=model, prompt=prompt, system=system)
    data = _extract_json(raw)
    return ExtractedIntent(
        project_type=_enum_or_none(ProjectType, data.get("project_type")),
        terraform_shape=_enum_or_none(TerraformShape, data.get("terraform_shape")),
        platform=_enum_or_none(Platform, data.get("platform")),
        purpose=data.get("purpose"),
        proposed_name=data.get("proposed_name"),
        confidence=_coerce_confidence(data.get("confidence")),
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
    additional_context: str = "",
) -> EvalVerdict:
    if harness.name == "heuristic":
        # Defer to deterministic gate; soft-pass once a name can be built.
        # Apply default_project_type here — extract often leaves type unset for
        # generic tickets (REPO-16), and the gate would still pass.
        from repo_vendor.config import get_settings
        from repo_vendor.naming import (
            _apply_default_type,
            build_proposed_name,
            select_template,
        )

        working = _apply_default_type(intent.model_copy(deep=True), get_settings())
        name = build_proposed_name(working)
        if name and working.project_type is not None and not intent.missing_info:
            return EvalVerdict(
                passed=True,
                proposed_name=name,
                template=select_template(working.project_type),
                reasons=["heuristic soft-pass; deterministic gate is authoritative"],
            )
        return EvalVerdict(
            passed=False,
            proposed_name=name,
            reasons=["heuristic eval: incomplete intent"],
            missing_info=intent.missing_info
            or ["Insufficient information for naming/template selection"],
        )

    from repo_vendor.cloud_docs import normalize_additional_context

    ctx = normalize_additional_context(additional_context) or "(none)"
    system, prompt = format_user_prompt(
        "judge-naming",
        summary=summary,
        description=description,
        intent_json=intent.model_dump_json(),
        additional_context=ctx,
    )
    raw = harness.complete(model=model, prompt=prompt, system=system)
    data = _extract_json(raw)
    return EvalVerdict(
        passed=_coerce_bool(data.get("passed")),
        proposed_name=data.get("proposed_name"),
        template=data.get("template"),
        reasons=list(data.get("reasons") or []),
        missing_info=list(data.get("missing_info") or []),
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


def _coerce_confidence(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        s = value.strip().lower()
        labels = {"high": 0.85, "medium": 0.6, "med": 0.6, "low": 0.35, "certain": 0.95}
        if s in labels:
            return labels[s]
        if s.endswith("%"):
            try:
                return max(0.0, min(1.0, float(s[:-1]) / 100.0))
            except ValueError:
                return 0.0
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    # Model sometimes returns 0-100 instead of 0-1
    if conf > 1.0 and conf <= 100.0:
        conf = conf / 100.0
    return max(0.0, min(1.0, conf))


def derive_confidence(intent: ExtractedIntent, *, gate_passed: bool = False) -> float:
    """Fill confidence when the LLM omitted it (common with agent JSON extracts)."""
    if intent.confidence > 0.0:
        return intent.confidence

    score = 0.35
    if intent.project_type is not None:
        score += 0.15
    if intent.purpose or intent.proposed_name:
        score += 0.15
    if intent.project_type == ProjectType.TERRAFORM:
        if intent.terraform_shape is not None:
            score += 0.1
        if intent.terraform_shape == TerraformShape.MODULE:
            if intent.platform is not None:
                score += 0.15
        elif intent.terraform_shape == TerraformShape.ROOT:
            score += 0.1
    elif intent.project_type == ProjectType.PYTHON:
        score += 0.1
    elif intent.project_type == ProjectType.GENERIC:
        score += 0.05
    if not intent.missing_info:
        score += 0.1
    if gate_passed:
        score = max(score, 0.75)
        score += 0.05
    return max(0.0, min(1.0, round(score, 2)))


def _enum_or_none(enum_cls: type, value: Any):
    if value is None:
        return None
    try:
        return enum_cls(str(value).lower())
    except ValueError:
        return None
