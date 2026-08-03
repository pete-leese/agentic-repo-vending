# Observability (Grafana Cloud)

Propose/vend metrics export to **Grafana Cloud** via the OTLP/HTTP gateway when Cloud Agent (or local) env is set. Fail-open: missing/broken OTEL config keeps structured logs only.

## Env (Grafana Cloud connection tile)

| Variable | Purpose |
|----------|---------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | e.g. `https://otlp-gateway-<REGION>.grafana.net/otlp` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64(instanceId:token)>` |
| `OTEL_SERVICE_NAME` | Prefer `agentic-repo-vending` |
| `OTEL_RESOURCE_ATTRIBUTES` | Optional `k=v,k2=v2` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Optional ms (default `5000`) |

**Do not wrap the header value in quotes** in Cursor secrets. A trailing `"` makes OpenTelemetry drop auth and Grafana returns **401** (flush may still look successful). Prefer URL-encoded spaces (`Basic%20…`).

Install the exporter deps: `uv sync --extra otel` (included in `make sync` / Cloud Agent `environment.json`).

## Metrics (Prometheus names)

OTLP names are prefixed `repo_vend_` and dots become underscores. Grafana may add suffixes (`_total`, `_milliseconds_bucket`):

| Event | Prom-ish name | Type |
|-------|---------------|------|
| `span.<phase>` | `repo_vend_span_<phase>_milliseconds_…` | histogram (ms) |
| `eval.result` | `repo_vend_eval_result_total` | counter |
| `vend.result` | `repo_vend_vend_result_total` | counter |
| `llm.tokens` | `repo_vend_llm_tokens_total` | counter |

Useful labels: `issue_key`, `status`, `stage`, `model`, `reason`, `success`, `passed`.

## Grafana dashboard

Importable JSON (panels from post-MVP: vend rate, eval fails, p95 spans, tokens placeholder):

[`docs/grafana/repo-vend-dashboard.json`](grafana/repo-vend-dashboard.json)

1. Grafana Cloud → **Dashboards** → **New** → **Import**
2. Upload the JSON (or paste)
3. Pick your **Prometheus** / Mimir datasource when prompted
4. Set time range to at least the last few hours after a smoke/propose run

Service variable defaults from `service_name` (usually `agentic-repo-vending`).

> Note: `terraform-agentic-workflows` documents OTEL → Grafana conceptually but does not ship a dashboard JSON — this file is the repo-vend equivalent.

## Verify

```bash
uv run python -m repo_vendor doctor   # OTEL_EXPORTER_OTLP_ENDPOINT: True
uv run python -m repo_vendor metrics-smoke
# Explore → Prometheus: {__name__=~".*repo_vend.*"}
# Or open the imported Repo Vend dashboard
```

CLI flushes and shuts down the meter provider after each propose/vend so short Cloud Agent runs still export.

Propose **does** emit metrics (`span.propose`, eval, `vend.result`). Application Observability / Traces stays empty until we export OTEL traces.
