import asyncio
import threading
import time
from collections.abc import Callable, Coroutine, Iterator
from functools import partial
from typing import Any

import pytest

from mothersauce.recipes.concurrency import bounded_map, demo, fetch_all, gather_limited, run_workers


def test_fetch_all_keeps_order_and_errors() -> None:
    def fetch(n: int) -> int:
        time.sleep(0.01 * (5 - n))  # later keys finish first
        if n == 2:
            raise TimeoutError("slow supplier")
        return n * 10

    results = fetch_all(range(5), fetch, workers=5)
    assert list(results) == [0, 1, 2, 3, 4]
    assert results[0] == 0 and results[4] == 40
    assert isinstance(results[2], TimeoutError)


def test_fetch_all_overlaps_the_waiting() -> None:
    started = time.perf_counter()
    fetch_all(range(8), lambda n: time.sleep(0.05), workers=8)
    assert time.perf_counter() - started < 0.3


def test_bounded_map_never_exceeds_in_flight() -> None:
    lock = threading.Lock()
    running = peak = 0

    def work(n: int) -> int:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.002)
        with lock:
            running -= 1
        return n

    assert sorted(bounded_map(work, range(50), workers=8, in_flight=3)) == list(range(50))
    assert peak <= 3


def test_bounded_map_reads_the_stream_lazily() -> None:
    pulled: list[int] = []

    def stream() -> Iterator[int]:
        for n in range(1000):
            pulled.append(n)
            yield n

    results = bounded_map(lambda n: n, stream(), workers=2, in_flight=4)
    next(results)
    assert len(pulled) < 20
    results.close()


def make_jobs(count: int, tracker: dict[str, int], fail_at: int = -1) -> list[Callable[[], Coroutine[Any, Any, int]]]:
    async def job(n: int) -> int:
        tracker["running"] += 1
        tracker["peak"] = max(tracker["peak"], tracker["running"])
        await asyncio.sleep(0.01)
        tracker["running"] -= 1
        if n == fail_at:
            raise ValueError(f"job {n} failed")
        return n

    return [partial(job, n) for n in range(count)]


def test_gather_limited_respects_the_limit_and_order() -> None:
    tracker = {"running": 0, "peak": 0}
    assert asyncio.run(gather_limited(make_jobs(10, tracker), limit=2, timeout=5)) == list(range(10))
    assert tracker["peak"] == 2


def test_gather_limited_surfaces_failures_as_a_group() -> None:
    with pytest.raises(ExceptionGroup) as caught:
        asyncio.run(gather_limited(make_jobs(5, {"running": 0, "peak": 0}, fail_at=3), limit=5, timeout=5))
    assert caught.group_contains(ValueError, match="job 3 failed")


def test_gather_limited_enforces_the_deadline() -> None:
    async def slow() -> int:
        await asyncio.sleep(5)
        return 1

    with pytest.raises(TimeoutError):
        asyncio.run(gather_limited([slow], limit=1, timeout=0.05))


def test_run_workers_collects_results_and_errors() -> None:
    results, errors = run_workers(range(20), lambda n: 60 // (n % 5), workers=4)
    assert len(results) == 16 and len(errors) == 4
    assert all(isinstance(e, ZeroDivisionError) for e in errors)


def test_run_workers_stops_every_thread() -> None:
    before = threading.active_count()
    run_workers(range(5), str, workers=6)
    assert threading.active_count() == before


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "20 suppliers in" in out and "4 failed" in out
    assert "at most 3 at once" in out
