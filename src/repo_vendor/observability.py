"""Observability hooks — log sink by default; OTLP → Grafana Cloud when configured."""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Attribute keys that must never leave the process (secrets / large payloads).
_REDACT_ATTR_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "token",
        "password",
        "secret",
        "bearer",
        "webhook",
    }
)


@dataclass
class MetricEvent:
    name: str
    value: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)


class MetricsSink(ABC):
    """Emit business metrics; OTLP implementation exports to Grafana Cloud / collectors."""

    @abstractmethod
    def emit(self, event: MetricEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        raise NotImplementedError

    def flush(self, timeout_millis: int = 10_000) -> bool:
        """Best-effort export for short-lived CLI processes. Returns True if flushed."""
        return True

    def shutdown(self, timeout_millis: int = 10_000) -> None:
        """Release exporters. Default: flush then no-op."""
        self.flush(timeout_millis=timeout_millis)


class LoggingMetricsSink(MetricsSink):
    """Default sink: structured logs only."""

    def emit(self, event: MetricEvent) -> None:
        logger.info(
            "metric name=%s value=%s attrs=%s",
            event.name,
            event.value,
            event.attributes,
        )

    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        # Prefer direction labels over raw counts-as-labels (cardinality).
        if input_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=float(input_tokens),
                    attributes={"model": model, "direction": "input"},
                )
            )
        if output_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=float(output_tokens),
                    attributes={"model": model, "direction": "output"},
                )
            )
        if not input_tokens and not output_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=0.0,
                    attributes={"model": model, "direction": "total"},
                )
            )


class FanoutMetricsSink(MetricsSink):
    """Emit to multiple sinks (e.g. logs + OTLP). Failures in one sink do not block others."""

    def __init__(self, sinks: list[MetricsSink]) -> None:
        self._sinks = sinks

    def emit(self, event: MetricEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:
                logger.exception("metrics sink emit failed: %s", type(sink).__name__)

    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        for sink in self._sinks:
            try:
                sink.record_tokens(
                    model=model, input_tokens=input_tokens, output_tokens=output_tokens
                )
            except Exception:
                logger.exception("metrics sink record_tokens failed: %s", type(sink).__name__)

    def flush(self, timeout_millis: int = 10_000) -> bool:
        ok = True
        for sink in self._sinks:
            try:
                if not sink.flush(timeout_millis=timeout_millis):
                    ok = False
            except Exception:
                logger.exception("metrics sink flush failed: %s", type(sink).__name__)
                ok = False
        return ok

    def shutdown(self, timeout_millis: int = 10_000) -> None:
        for sink in self._sinks:
            try:
                sink.shutdown(timeout_millis=timeout_millis)
            except Exception:
                logger.exception("metrics sink shutdown failed: %s", type(sink).__name__)


class OtlpMetricsSink(MetricsSink):
    """Export metrics via OTLP/HTTP (Grafana Cloud OTLP gateway or any collector).

    Reads standard env vars:
    - ``OTEL_EXPORTER_OTLP_ENDPOINT`` (required to enable)
    - ``OTEL_EXPORTER_OTLP_HEADERS`` (e.g. ``Authorization=Basic …``)
    - ``OTEL_EXPORTER_OTLP_PROTOCOL`` (``http/protobuf``)
    - ``OTEL_SERVICE_NAME`` (default ``agentic-repo-vending``)
    - ``OTEL_RESOURCE_ATTRIBUTES`` (optional ``k=v,k2=v2``)
    """

    def __init__(self, *, meter: Any, provider: Any) -> None:
        self._meter = meter
        self._provider = provider
        self._histograms: dict[str, Any] = {}
        self._counters: dict[str, Any] = {}

    @classmethod
    def from_env(cls) -> OtlpMetricsSink:
        try:
            from opentelemetry import metrics
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
        except ImportError as exc:
            raise RuntimeError(
                "OTLP metrics require the 'otel' extra: uv sync --extra otel"
            ) from exc

        service_name = os.environ.get("OTEL_SERVICE_NAME", "").strip() or "agentic-repo-vending"
        resource_attrs: dict[str, str] = {"service.name": service_name}
        resource_attrs.update(
            _parse_resource_attributes(os.environ.get("OTEL_RESOURCE_ATTRIBUTES"))
        )

        # Short-lived CLI: export often + always flush on shutdown.
        export_interval = int(os.environ.get("OTEL_METRIC_EXPORT_INTERVAL", "5000"))
        exporter = OTLPMetricExporter()
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=export_interval,
        )
        provider = MeterProvider(
            resource=Resource.create(resource_attrs),
            metric_readers=[reader],
        )
        metrics.set_meter_provider(provider)
        meter = metrics.get_meter("repo_vendor", version="0.1.0")
        return cls(meter=meter, provider=provider)

    def emit(self, event: MetricEvent) -> None:
        attrs = _otel_attributes(event.attributes)
        if event.name.startswith("span."):
            hist = self._histogram(event.name, unit="ms")
            hist.record(event.value, attrs)
            return
        counter = self._counter(event.name)
        counter.add(event.value, attrs)

    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        if input_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=float(input_tokens),
                    attributes={"model": model, "direction": "input"},
                )
            )
        if output_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=float(output_tokens),
                    attributes={"model": model, "direction": "output"},
                )
            )
        if not input_tokens and not output_tokens:
            self.emit(
                MetricEvent(
                    name="llm.tokens",
                    value=0.0,
                    attributes={"model": model, "direction": "total"},
                )
            )

    def flush(self, timeout_millis: int = 10_000) -> bool:
        return bool(self._provider.force_flush(timeout_millis=timeout_millis))

    def shutdown(self, timeout_millis: int = 10_000) -> None:
        self._provider.shutdown(timeout_millis=timeout_millis)

    def _histogram(self, name: str, *, unit: str = "1") -> Any:
        if name not in self._histograms:
            self._histograms[name] = self._meter.create_histogram(
                name=_prom_safe_name(name),
                unit=unit,
                description=f"repo-vendor {name}",
            )
        return self._histograms[name]

    def _counter(self, name: str) -> Any:
        if name not in self._counters:
            self._counters[name] = self._meter.create_counter(
                name=_prom_safe_name(name),
                description=f"repo-vendor {name}",
            )
        return self._counters[name]


_sink: MetricsSink = LoggingMetricsSink()


def set_metrics_sink(sink: MetricsSink) -> None:
    global _sink
    _sink = sink


def get_metrics_sink() -> MetricsSink:
    return _sink


def otlp_endpoint_configured() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def normalize_otlp_headers_env() -> bool:
    """Strip accidental quotes from OTEL header env vars (common secrets-UI footgun).

    Grafana Cloud returns 401 when the header string is invalid (e.g. trailing ``"``),
    while ``force_flush`` can still report success. Returns True if any value changed.
    """
    changed = False
    for key in (
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
    ):
        raw = os.environ.get(key)
        if raw is None:
            continue
        cleaned = _strip_env_quotes(raw)
        if cleaned != raw:
            os.environ[key] = cleaned
            changed = True
            logger.warning(
                "Normalized %s: removed surrounding/trailing quotes "
                "(invalid quotes cause Grafana OTLP 401)",
                key,
            )
    return changed


def configure_metrics_from_env(*, also_log: bool = True) -> MetricsSink:
    """Select sink from env. Fail-open to logging if OTLP is unset or misconfigured."""
    if not otlp_endpoint_configured():
        sink: MetricsSink = LoggingMetricsSink()
        set_metrics_sink(sink)
        return sink

    normalize_otlp_headers_env()

    try:
        otlp = OtlpMetricsSink.from_env()
    except Exception:
        logger.exception(
            "OTLP metrics disabled (fail-open); check OTEL_* env and `uv sync --extra otel`"
        )
        sink = LoggingMetricsSink()
        set_metrics_sink(sink)
        return sink

    sink = FanoutMetricsSink([LoggingMetricsSink(), otlp]) if also_log else otlp
    set_metrics_sink(sink)
    logger.info(
        "OTLP metrics enabled endpoint=%s service=%s",
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/"),
        os.environ.get("OTEL_SERVICE_NAME", "agentic-repo-vending"),
    )
    return sink


def flush_metrics(timeout_millis: int = 10_000) -> bool:
    ok = get_metrics_sink().flush(timeout_millis=timeout_millis)
    if not ok:
        logger.error(
            "OTLP metrics flush failed/timed out — check exporter ERROR logs "
            "(Grafana often returns 401 for bad OTEL_EXPORTER_OTLP_HEADERS)"
        )
    return ok


def shutdown_metrics(timeout_millis: int = 10_000) -> None:
    get_metrics_sink().shutdown(timeout_millis=timeout_millis)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """Timing span — duration exported as histogram ``span.<name>`` (ms)."""
    start = time.perf_counter()
    try:
        yield
        status = "ok"
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        _sink.emit(
            MetricEvent(
                name=f"span.{name}",
                value=duration_ms,
                attributes={**attributes, "status": status},
            )
        )


def record_eval(passed: bool, **attributes: Any) -> None:
    _sink.emit(
        MetricEvent(
            name="eval.result",
            value=1.0 if passed else 0.0,
            attributes={**attributes, "passed": passed},
        )
    )


def record_vend(success: bool, **attributes: Any) -> None:
    _sink.emit(
        MetricEvent(
            name="vend.result",
            value=1.0 if success else 0.0,
            attributes={**attributes, "success": success},
        )
    )


def _strip_env_quotes(raw: str) -> str:
    """Remove wrapping quotes and a single trailing quote leftover from secret UIs."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    # Secrets UIs sometimes store Authorization=…\" with only a trailing quote.
    while text.endswith('"') or text.endswith("'"):
        text = text[:-1].rstrip()
    return text


def _prom_safe_name(name: str) -> str:
    """OTLP→Prometheus prefers ``_``; keep a stable prefix."""
    cleaned = name.replace(".", "_").replace("-", "_")
    if not cleaned.startswith("repo_vend_"):
        cleaned = f"repo_vend_{cleaned}"
    return cleaned


def _parse_resource_attributes(raw: str | None) -> dict[str, str]:
    if not raw or not raw.strip():
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key and value:
            out[key] = value
    return out


def _otel_attributes(attributes: dict[str, Any]) -> dict[str, str | bool | int | float]:
    out: dict[str, str | bool | int | float] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        lower = key.lower()
        if lower in _REDACT_ATTR_KEYS or any(s in lower for s in _REDACT_ATTR_KEYS):
            continue
        if isinstance(value, bool | int | float):
            out[key] = value
        else:
            text = str(value)
            # Cap label cardinality / payload size for Grafana Cloud.
            out[key] = text if len(text) <= 256 else text[:253] + "..."
    return out
