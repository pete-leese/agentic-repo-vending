"""Observability hooks — no-op/log sink in MVP; OTEL/Grafana post-MVP."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class MetricEvent:
    name: str
    value: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)


class MetricsSink(ABC):
    """Post-MVP: implement OTLP exporter → Grafana."""

    @abstractmethod
    def emit(self, event: MetricEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        raise NotImplementedError


class LoggingMetricsSink(MetricsSink):
    """MVP sink: structured logs only."""

    def emit(self, event: MetricEvent) -> None:
        logger.info(
            "metric name=%s value=%s attrs=%s",
            event.name,
            event.value,
            event.attributes,
        )

    def record_tokens(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        self.emit(
            MetricEvent(
                name="llm.tokens",
                value=float(input_tokens + output_tokens),
                attributes={
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
        )


_sink: MetricsSink = LoggingMetricsSink()


def set_metrics_sink(sink: MetricsSink) -> None:
    global _sink
    _sink = sink


def get_metrics_sink() -> MetricsSink:
    return _sink


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """MVP timing span — replace with OTEL tracer post-MVP."""
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
