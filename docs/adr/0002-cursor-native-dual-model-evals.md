# ADR 0002: Cursor-native dual-model evals with deterministic gate

## Status

Accepted

## Context

Naming and template selection must be enforced reliably. A single model both proposing and judging its own output is weak. External LLM provider keys add demo friction.

## Decision

- Orchestrator LLM: Anthropic `claude-sonnet-5` via Cursor (intent extraction; Other Models pool).
- Eval judge LLM: Cursor model `composer-2.5` (must differ from orchestrator; Cursor Models pool).
- Earlier iterations used `composer-2.5`/`composer-2` then swapped Sonnet onto the judge; current preference is Sonnet on **propose/extract** and Composer on **eval**.
- Deterministic kebab/pattern/template rules always run; hard-fail overrides any LLM pass.
- Platform may be derived from cloud-specific services (EKS→aws, GKE→gcp, AKS→azure) in addition to labels.
- Access Cursor models via Cursor SDK from the PydanticAI app; Cloud Automation runtime stays on `composer-2.5` (tooling + CLI orchestration, separate from eval IDs).

## Consequences

- One `CURSOR_API_KEY` covers LLM calls for MVP; orchestrator usage draws from the Other Models pool.
- Model IDs are centralized in `repo-vend.yaml` and overridable by `ORCHESTRATOR_MODEL` / `EVAL_MODEL`.
- Post-MVP harnesses can replace the Cursor SDK adapter without changing domain rules.
