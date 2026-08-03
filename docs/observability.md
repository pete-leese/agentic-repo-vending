# Observability (Grafana Cloud)

Propose/vend metrics export to **Grafana Cloud** via the OTLP/HTTP gateway when Cloud Agent (or local) env is set. Fail-open: missing/broken OTEL config keeps structured logs only.

## Env (Grafana Cloud connection tile)

| Variable | Purpose |
|----------|---------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | e.g. `https://otlp-gateway-<REGION>.grafana.net/otlp` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic <base64(instanceId:token)>` |
| `OTEL_SERVICE_NAME` | Prefer `agentic-repo-vending` |
| `OTEL_RESOURCE_ATTRIBUTES` | Optional `k=v,k2=v2` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Optional ms (default `5000`) |

Install the exporter deps: `uv sync --extra otel` (included in `make sync` / Cloud Agent `environment.json`).

## Metrics (Prometheus names)

OTLP names are prefixed `repo_vend_` and dots become underscores:

| Event | Prom-ish name | Type |
|-------|---------------|------|
| `span.<phase>` | `repo_vend_span_<phase>` | histogram (ms) |
| `eval.result` | `repo_vend_eval_result` | counter |
| `vend.result` | `repo_vend_vend_result` | counter |
| `llm.tokens` | `repo_vend_llm_tokens` | counter |

Useful labels: `issue_key`, `status`, `stage`, `model`, `reason`, `success`, `passed`.

## Verify

```bash
uv run python -m repo_vendor doctor   # OTEL_EXPORTER_OTLP_ENDPOINT: True
# Run propose/vend once, then Explore in Grafana Cloud → Metrics
```

CLI flushes and shuts down the meter provider after each propose/vend so short Cloud Agent runs still export.
