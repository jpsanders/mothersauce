"""
Concurrency: wait for many slow things at once, with limits, and never lose an error.

Most data work waits: on an API, a database, object storage. Threads and asyncio let that waiting overlap, so fifty
requests of half a second take a few seconds instead of twenty five. Work that computes rather than waits needs
processes, or the free threaded build of Python, which runs threads truly in parallel since 3.14.

Production rules:

- Bound the concurrency. An unbounded fan out is a denial of service on your own database.
- Bound what is in flight too: submitting ten million futures at once holds ten million futures in memory.
- Collect errors per item. One failed request must not hide the other forty nine results.
- Keep results in input order when the caller expects it, whatever order they finished in.
- Shut workers down explicitly: a sentinel value per worker, or a context manager that does it for you.
"""

import asyncio
import queue
import threading
import time
from collections.abc import Awaitable, Callable, Generator, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait

__all__ = ["bounded_map", "demo", "fetch_all", "gather_limited", "run_workers"]

_STOP = sentinel("_STOP")  # Python 3.15: a unique marker with a readable repr, the end of a worker's queue


def fetch_all[K, R](keys: Iterable[K], fetch: Callable[[K], R], workers: int = 8) -> dict[K, R | Exception]:
    """
    Call ``fetch`` for every key on a thread pool and keep each result or each exception, in input order.

    :param keys: What to fetch, such as supplier ids
    :param fetch: A function that waits on input and output
    :param workers: The most calls in flight at once
    :returns: For each key, its result or the exception it raised
    """
    ordered = list(keys)
    results: dict[K, R | Exception] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fetch") as pool:
        futures = {pool.submit(fetch, key): key for key in ordered}
        for future, key in futures.items():
            error = future.exception()
            results[key] = future.result() if error is None else error  # type: ignore[assignment]
    return {key: results[key] for key in ordered}


def bounded_map[T, R](
    func: Callable[[T], R], items: Iterable[T], workers: int = 4, in_flight: int = 16
) -> Generator[tuple[T, R | Exception]]:
    """
    Map over a stream of any length with at most ``in_flight`` calls submitted at a time, yielding as they finish.

    A failure is yielded like a result, next to the item that caused it, so one bad item never hides the rest.

    :param func: The function to run on each item
    :param items: The stream; it is read only as fast as the workers keep up
    :param workers: Threads in the pool
    :param in_flight: The most submitted but unfinished calls
    :yields: Each item with its result or its exception, in completion order
    """

    def outcome(future: Future[R]) -> R | Exception:
        error = future.exception()
        return future.result() if error is None else error  # type: ignore[return-value]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: dict[Future[R], T] = {}
        for item in items:
            if len(pending) >= in_flight:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    yield pending.pop(future), outcome(future)
            pending[pool.submit(func, item)] = item
        for future in as_completed(pending):
            yield pending[future], outcome(future)


async def gather_limited[R](jobs: Iterable[Callable[[], Awaitable[R]]], limit: int, timeout: float) -> list[R]:
    """
    Run coroutines with at most ``limit`` at a time and an overall deadline; results come back in input order.

    ``TaskGroup`` cancels the rest when one fails, so nothing keeps running after the caller has moved on.

    :param jobs: Functions that each return a fresh coroutine
    :param limit: The most running at once
    :param timeout: Seconds for the whole batch
    :returns: The results, in input order
    """
    gate = asyncio.Semaphore(limit)

    async def limited(job: Callable[[], Awaitable[R]]) -> R:
        async with gate:
            return await job()

    async with asyncio.timeout(timeout):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(limited(job)) for job in jobs]
    return [task.result() for task in tasks]


def run_workers[J, R](jobs: Iterable[J], handle: Callable[[J], R], workers: int = 4) -> tuple[list[R], list[Exception]]:
    """
    A dispatcher: worker threads take jobs from a queue until each receives the stop marker.

    :param jobs: The jobs
    :param handle: What a worker does with one job
    :param workers: How many workers
    :returns: The results and the errors, each in completion order
    """
    inbox: queue.Queue[J | object] = queue.Queue(maxsize=workers * 4)  # bounded: the producer waits for the workers
    results: list[R] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def work() -> None:
        while (job := inbox.get()) is not _STOP:
            try:
                outcome = handle(job)  # type: ignore[arg-type]  # anything but the stop marker is a job
            except Exception as error:  # a worker must survive any job; the error is kept, not lost
                with lock:
                    errors.append(error)
            else:
                with lock:
                    results.append(outcome)
            finally:
                inbox.task_done()
        inbox.task_done()

    threads = [threading.Thread(target=work, name=f"worker-{n}", daemon=True) for n in range(workers)]
    for thread in threads:
        thread.start()
    for job in jobs:
        inbox.put(job)
    for _ in threads:
        inbox.put(_STOP)
    for thread in threads:
        thread.join()
    return results, errors


def demo() -> None:
    """Fan out slow calls on threads and on asyncio, bounded, keeping every error."""

    def supplier_price(supplier: str) -> float:
        time.sleep(0.05)  # stands for a network call
        if supplier.startswith("closed"):
            raise ConnectionError(f"{supplier} did not answer")
        return 4.5 + len(supplier) / 10

    names = ["fish market", "dairy", "closed on mondays", "greengrocer", "butcher"]
    suppliers = [f"{name} {district}" for district in ("north", "south", "east", "west") for name in names]
    started = time.perf_counter()
    prices = fetch_all(suppliers, supplier_price, workers=8)
    elapsed = time.perf_counter() - started
    failed = [k for k, v in prices.items() if isinstance(v, Exception)]
    print(f"{len(prices)} suppliers in {elapsed:.2f}s instead of {0.05 * len(prices):.2f}s; {len(failed)} failed")
    outcomes = bounded_map(lambda n: n * n, range(1000), workers=4, in_flight=8)
    squares = sorted(result for _, result in outcomes if not isinstance(result, Exception))
    print(f"bounded_map over 1,000 items, never more than 8 in flight: sum {sum(squares):,}")
    running = peak = 0

    async def fake_call(n: int) -> int:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return n

    jobs = [lambda n=n: fake_call(n) for n in range(12)]
    results = asyncio.run(gather_limited(jobs, limit=3, timeout=2))
    print(f"asyncio: {len(results)} calls, in order {results == list(range(12))}, at most {peak} at once")
    done, failures = run_workers(range(10), lambda n: 100 // (n - 3), workers=3)
    print(f"workers: {len(done)} done, {len(failures)} failed ({failures[0]!r}), and every worker stopped cleanly")
