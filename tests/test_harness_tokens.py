from __future__ import annotations

from types import SimpleNamespace

from repo_vendor.harness import _record_run_tokens
from repo_vendor.observability import (
    LoggingMetricsSink,
    MetricEvent,
    set_metrics_sink,
)


def test_record_run_tokens_from_usage():
    class Capture(LoggingMetricsSink):
        def __init__(self) -> None:
            self.events: list[MetricEvent] = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    sink = Capture()
    set_metrics_sink(sink)
    waited = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=10, output_tokens=3, total_tokens=13)
    )
    _record_run_tokens(model="claude-sonnet-5", waited=waited)
    assert len(sink.events) == 2
    assert sink.events[0].attributes["direction"] == "input"
    assert sink.events[0].value == 10.0
    assert sink.events[1].attributes["direction"] == "output"
    assert sink.events[1].attributes["model"] == "claude-sonnet-5"
    set_metrics_sink(LoggingMetricsSink())


def test_record_run_tokens_total_only():
    class Capture(LoggingMetricsSink):
        def __init__(self) -> None:
            self.events: list[MetricEvent] = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    sink = Capture()
    set_metrics_sink(sink)
    waited = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=0, output_tokens=0, total_tokens=42)
    )
    _record_run_tokens(model="composer-2.5", waited=waited)
    assert len(sink.events) == 1
    assert sink.events[0].attributes["direction"] == "total"
    assert sink.events[0].value == 42.0
    set_metrics_sink(LoggingMetricsSink())


def test_record_run_tokens_missing_usage_noop():
    class Capture(LoggingMetricsSink):
        def __init__(self) -> None:
            self.events: list[MetricEvent] = []

        def emit(self, event: MetricEvent) -> None:
            self.events.append(event)

    sink = Capture()
    set_metrics_sink(sink)
    _record_run_tokens(model="x", waited=SimpleNamespace())
    assert sink.events == []
    set_metrics_sink(LoggingMetricsSink())
