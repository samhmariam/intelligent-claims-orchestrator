from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

try:
    from opentelemetry import trace
    from opentelemetry.trace import Span
except Exception:  # pragma: no cover - optional dependency
    trace = None
    Span = None  # type: ignore[misc,assignment]


@contextmanager
def start_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[None]:
    if trace is None:
        yield
        return
    tracer = trace.get_tracer("icpa")
    with tracer.start_as_current_span(name) as span:  # type: ignore[union-attr]
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield


def annotate_span(attributes: Dict[str, Any]) -> None:
    if trace is None:
        return
    span = trace.get_current_span()
    if span is None:
        return
    for key, value in attributes.items():
        span.set_attribute(key, value)
