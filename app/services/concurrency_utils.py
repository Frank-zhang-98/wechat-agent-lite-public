from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import BoundedSemaphore
from urllib.parse import urlparse
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def normalized_host(url: str) -> str:
    host = urlparse(str(url or "")).netloc.lower().split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host or "__default__"


def iter_host_limited_results(
    tasks: Iterable[T],
    *,
    worker_fn: Callable[[T], R],
    host_getter: Callable[[T], str],
    max_workers: int,
    per_host_limit: int,
    overall_timeout_seconds: float | None = None,
) -> Iterable[tuple[T, R | None, Exception | None]]:
    task_list = list(tasks)
    if not task_list:
        return []

    worker_count = max(1, int(max_workers))
    host_limit = max(1, int(per_host_limit))
    semaphores = {
        host: BoundedSemaphore(host_limit)
        for host in {host_getter(task) or "__default__" for task in task_list}
    }

    def guarded_worker(task: T) -> R:
        host = host_getter(task) or "__default__"
        semaphore = semaphores[host]
        with semaphore:
            return worker_fn(task)

    def generator() -> Iterable[tuple[T, R | None, Exception | None]]:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(guarded_worker, task): task for task in task_list}
            pending = set(future_map)
            deadline = None if overall_timeout_seconds is None else time.monotonic() + max(0.0, float(overall_timeout_seconds))
            while pending:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining == 0:
                    break
                done, pending = wait(
                    pending,
                    timeout=remaining,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    break
                for future in done:
                    task = future_map[future]
                    try:
                        yield task, future.result(), None
                    except Exception as exc:  # pragma: no cover - exercised via callers
                        yield task, None, exc
            if pending:
                timeout_error = TimeoutError("overall_timeout_exceeded")
                for future in pending:
                    future.cancel()
                    yield future_map[future], None, timeout_error

    return generator()
