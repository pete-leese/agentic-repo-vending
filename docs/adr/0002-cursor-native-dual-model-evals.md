# ADR 0002: Cursor-native dual-model evals with deterministic gate

## Status

Accepted

## Context

Naming and template selection must be enforced reliably. A single model both proposing and judging its own output is weak. External LLM provider keys add demo friction.

## Decision

- Orchestrator LLM: Cursor model `composer-2.5` (intent extraction; Cursor Models pool).
- Eval judge LLM: Anthropic `claude-sonnet-5` via Cursor (must differ from orchestrator; Other Models pool).
- Earlier MVP used `composer-2` as judge; Sonnet 5 is preferred for stricter naming/template judgment at Sonnet pricing (promo through Aug 2026).
- Deterministic kebab/pattern/template rules always run; hard-fail overrides any LLM pass.
- Access Cursor models via Cursor SDK from the PydanticAI app; Cloud Automation runtime stays on `composer-2.5` (tooling + CLI orchestration, separate from eval IDs).

## Consequences

- One `CURSOR_API_KEY` covers LLM calls for MVP; judge usage draws from the Other Models pool.
- Model IDs are centralized in `repo-vend.yaml` and overridable by `ORCHESTRATOR_MODEL` / `EVAL_MODEL`.
- Post-MVP harnesses can replace the Cursor SDK adapter without changing domain rules.
