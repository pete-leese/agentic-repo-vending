# Post-MVP (do not build yet)

Signed off MVP first, then implement these. The MVP already leaves extension points.

## 1. OpenTelemetry → Grafana

**Goal:** Observe latency, token usage, eval pass/fail, vend success/skip.

**Shipped (OTLP → Grafana Cloud):**

- [`src/repo_vendor/observability.py`](../src/repo_vendor/observability.py) — `MetricsSink`, `OtlpMetricsSink`, `span()`, `record_eval()`, `record_vend()`
- CLI bootstraps from `OTEL_*` env and flushes on exit (see [`docs/observability.md`](observability.md))
- Default sink: structured logs; with endpoint set: logs + OTLP (fail-open)

**Still open:**

1. ~~Grafana dashboard panels~~ → [`docs/grafana/repo-vend-dashboard.json`](grafana/repo-vend-dashboard.json)
2. HITL wait metrics (`hitl.latency_ms` / `hitl.result`)
3. Optional real OTEL traces (today spans are duration histograms only)
4. ~~Wire `record_tokens()`~~ → Cursor SDK `RunResult.usage` on extract/judge (heuristic harness: no tokens)

## 2. Additional AI harnesses

**Goal:** Run the same vend graph on Harness / other agent runtimes without rewriting domain rules.

**MVP hooks:**

- [`src/repo_vendor/harness.py`](../src/repo_vendor/harness.py) — `ModelHarness` ABC, `CursorSdkHarness`, `HeuristicHarness`
- Naming rules stay in [`naming.py`](../src/repo_vendor/naming.py) (harness-agnostic)
- PydanticAI typed agents in [`agents.py`](../src/repo_vendor/agents.py)

**Phase 2 work:**

1. Add `HarnessXAdapter(ModelHarness)`
2. Select via env `MODEL_HARNESS=cursor|harness|...`
3. Keep dual-model eval policy (orchestrator ≠ judge) + deterministic gate

## Checklist before starting Phase 2

- [ ] MVP demo paths A–D signed off
- [ ] Templates stable
- [ ] Webhook reliability acceptable
- [ ] Rotate any exposed API keys
- [x] OTEL env available on Cloud Agent + `otel` extra installed
