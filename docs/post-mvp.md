# Post-MVP (do not build yet)

Signed off MVP first, then implement these. The MVP already leaves extension points.

## 1. OpenTelemetry → Grafana

**Goal:** Observe latency, token usage, eval pass/fail, vend success/skip.

**MVP hooks (already present):**

- [`src/repo_vendor/observability.py`](../src/repo_vendor/observability.py) — `MetricsSink`, `span()`, `record_eval()`, `record_vend()`
- Default sink: structured logs only (`LoggingMetricsSink`)

**Phase 2 work:**

1. Implement `OtlpMetricsSink` exporting to your collector
2. Call `set_metrics_sink(...)` at process start
3. Grafana dashboard panels: vend rate, eval fail reasons, p95 span duration, tokens by model (`claude-sonnet-5` vs `composer-2.5`)

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
