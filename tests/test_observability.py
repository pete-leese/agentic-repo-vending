from __future__ import annotations

import pytest

from repo_vendor.observability import (
    FanoutMetricsSink,
    LoggingMetricsSink,
    MetricEvent,
    OtlpMetricsSink,
    _base_metric_attributes,
    _otel_attributes,
    _prom_safe_name,
    _strip_env_quotes,
    configure_metrics_from_env,
    get_metrics_sink,
    normalize_otlp_headers_env,
    otlp_endpoint_configured,
    set_metrics_sink,
    span,
)


def test_metrics_sink_default():
    set_metrics_sink(LoggingMetricsSink())
    assert isinstance(get_metrics_sink(), LoggingMetricsSink)
    get_metrics_sink().emit(MetricEvent(name="test", value=1.0))


def test_set_metrics_sink():
    class Capture(LoggingMetricsSink):
        def __init__(self):
            self.events = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    sink = Capture()
    set_metrics_sink(sink)
    sink.emit(MetricEvent(name="x", value=2))
    assert sink.events[0].name == "x"
    set_metrics_sink(LoggingMetricsSink())


def test_strip_env_quotes():
    assert _strip_env_quotes('"Authorization=Basic abc=="') == "Authorization=Basic abc=="
    assert _strip_env_quotes('Authorization=Basic abc=="') == "Authorization=Basic abc=="
    assert _strip_env_quotes("Authorization=Basic abc==") == "Authorization=Basic abc=="


def test_normalize_otlp_headers_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_HEADERS",
        '"Authorization=Basic%20dGVzdA=="',
    )
    assert normalize_otlp_headers_env() is True
    assert (
        __import__("os").environ["OTEL_EXPORTER_OTLP_HEADERS"] == "Authorization=Basic%20dGVzdA=="
    )
    assert normalize_otlp_headers_env() is False


def test_otlp_endpoint_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert otlp_endpoint_configured() is False
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp-gateway.example/otlp")
    assert otlp_endpoint_configured() is True


def test_configure_metrics_fail_open_without_endpoint(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    sink = configure_metrics_from_env()
    assert isinstance(sink, LoggingMetricsSink)


def test_configure_metrics_fail_open_when_otel_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp-gateway.example/otlp")

    @classmethod
    def boom(cls: type[OtlpMetricsSink]) -> OtlpMetricsSink:
        raise RuntimeError("OTLP metrics require the 'otel' extra")

    monkeypatch.setattr(OtlpMetricsSink, "from_env", boom)
    sink = configure_metrics_from_env()
    assert isinstance(sink, LoggingMetricsSink)


def test_fanout_continues_on_sink_error():
    class Bad(LoggingMetricsSink):
        def emit(self, event: MetricEvent) -> None:
            raise RuntimeError("boom")

    class Capture(LoggingMetricsSink):
        def __init__(self) -> None:
            self.events: list[MetricEvent] = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    good = Capture()
    FanoutMetricsSink([Bad(), good]).emit(MetricEvent(name="ok", value=1.0))
    assert len(good.events) == 1


def test_span_emits_duration():
    class Capture(LoggingMetricsSink):
        def __init__(self) -> None:
            self.events: list[MetricEvent] = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    sink = Capture()
    set_metrics_sink(sink)
    with span("propose", issue_key="REPO-1"):
        pass
    assert sink.events[0].name == "span.propose"
    assert sink.events[0].value >= 0
    assert sink.events[0].attributes["status"] == "ok"
    assert sink.events[0].attributes["issue_key"] == "REPO-1"
    set_metrics_sink(LoggingMetricsSink())


def test_prom_safe_name():
    assert _prom_safe_name("span.propose") == "repo_vend_span_propose"
    assert _prom_safe_name("eval.result") == "repo_vend_eval_result"


def test_base_metric_attributes_adds_service_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "repo-vend-test")
    attrs = _base_metric_attributes({"issue_key": "REPO-1"})
    assert attrs["service_name"] == "repo-vend-test"
    assert attrs["issue_key"] == "REPO-1"


def test_base_metric_attributes_does_not_override_service_name(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
    attrs = _base_metric_attributes({"service_name": "explicit"})
    assert attrs["service_name"] == "explicit"


def test_otel_attributes_redact_and_truncate():
    attrs = _otel_attributes(
        {
            "issue_key": "REPO-1",
            "api_key": "secret",
            "token": "x",
            "ok": True,
            "n": 3,
            "big": "x" * 300,
            "none": None,
        }
    )
    assert attrs["issue_key"] == "REPO-1"
    assert attrs["ok"] == "true"
    assert attrs["n"] == 3
    assert "api_key" not in attrs
    assert "token" not in attrs
    assert "none" not in attrs
    assert isinstance(attrs["big"], str)
    assert len(attrs["big"]) <= 256


def test_configure_metrics_otlp_when_available(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("opentelemetry.exporter.otlp.proto.http.metric_exporter")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://otlp-gateway.example/otlp",
    )
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentic-repo-vending-test")

    # Avoid network: swap PeriodicExportingMetricReader construction path via from_env internals.
    def fake_from_env(cls: type[OtlpMetricsSink]) -> OtlpMetricsSink:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        reader = InMemoryMetricReader()
        provider = MeterProvider(
            resource=Resource.create({"service.name": "agentic-repo-vending-test"}),
            metric_readers=[reader],
        )
        metrics.set_meter_provider(provider)
        return cls(meter=metrics.get_meter("repo_vendor"), provider=provider)

    monkeypatch.setattr(OtlpMetricsSink, "from_env", classmethod(fake_from_env))
    sink = configure_metrics_from_env(also_log=True)
    assert isinstance(sink, FanoutMetricsSink)
    sink.emit(MetricEvent(name="span.test", value=1.5, attributes={"status": "ok"}))
    assert sink.flush(timeout_millis=1000) is True
    sink.shutdown(timeout_millis=1000)
    set_metrics_sink(LoggingMetricsSink())
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
