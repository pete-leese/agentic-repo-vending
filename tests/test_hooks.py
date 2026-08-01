from repo_vendor.config import Settings
from repo_vendor.harness import HeuristicHarness, get_harness
from repo_vendor.observability import (
    LoggingMetricsSink,
    MetricEvent,
    get_metrics_sink,
    set_metrics_sink,
)


def test_metrics_sink_default():
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


def test_heuristic_harness_when_no_key():
    settings = Settings(CURSOR_API_KEY="", ALLOW_LLM_FALLBACK=True)
    h = get_harness(settings)
    assert isinstance(h, HeuristicHarness)
    assert h.name == "heuristic"
