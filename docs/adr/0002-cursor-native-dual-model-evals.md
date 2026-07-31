# ADR 0002: Cursor-native dual-model evals with deterministic gate

## Status

Accepted

## Context

Naming and template selection must be enforced reliably. A single model both proposing and judging its own output is weak. External LLM provider keys add demo friction.

## Decision

- Orchestrator LLM: Cursor model `composer-2.5` (intent extraction).
- Eval judge LLM: Cursor model `composer-2` (must differ from orchestrator).
- Deterministic kebab/pattern/template rules always run; hard-fail overrides any LLM pass.
- Access Cursor models via Cursor SDK from the PydanticAI app; Cloud Automation runtime also uses `composer-2.5`.

## Consequences

- One `CURSOR_API_KEY` covers LLM calls for MVP.
- Model IDs are centralized in config and overridable by env.
- Post-MVP harnesses can replace the Cursor SDK adapter without changing domain rules.
