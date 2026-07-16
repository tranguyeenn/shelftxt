from __future__ import annotations

import time
from contextvars import ContextVar
from collections import defaultdict
from typing import Any

from fastapi import Request


_current_request: ContextVar[Request | None] = ContextVar("current_request", default=None)


def set_current_request(request: Request):
    return _current_request.set(request)


def reset_current_request(token) -> None:
    _current_request.reset(token)


def current_request() -> Request | None:
    return _current_request.get()


def init_request_timing(request: Request) -> None:
    request.state.stage_timings = defaultdict(float)
    request.state.stage_counts = defaultdict(int)


def add_timing(name: str, elapsed_ms: float, *, count: int = 1, request: Request | None = None) -> None:
    target = request or current_request()
    if target is None:
        return
    if not hasattr(target.state, "stage_timings"):
        init_request_timing(target)
    target.state.stage_timings[name] += elapsed_ms
    target.state.stage_counts[name] += count


class timed_stage:
    def __init__(self, name: str, *, request: Request | None = None) -> None:
        self.name = name
        self.request = request
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        add_timing(self.name, (time.perf_counter() - self.started) * 1000, request=self.request)


def timing_snapshot(request: Request) -> dict[str, Any]:
    timings = getattr(request.state, "stage_timings", {})
    counts = getattr(request.state, "stage_counts", {})
    payload: dict[str, Any] = {}
    for name, value in sorted(timings.items()):
        payload[f"{name}_ms"] = round(float(value), 2)
    for name, value in sorted(counts.items()):
        payload[f"{name}_count"] = int(value)
    return payload
