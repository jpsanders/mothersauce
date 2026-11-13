"""
Performance: measure first, then make the common path cheap.

Guesses about where time goes are usually wrong, so measure. ``timeit`` times a small piece, ``python -X importtime``
shows what start up costs, and Python 3.15 ships a sampling profiler, ``python -m profiling.sampling``, that watches a
running program without slowing it down.

The wins that hold up in production:

- ``lazy import`` (new in Python 3.15) loads a module on first use, so a CLI starts in milliseconds. This one does.
- Generators instead of lists for anything streamed, and ``__slots__`` for objects made by the million.
- ``functools.cache`` for pure functions, a ``set`` for membership, and ``str.join`` instead of ``+=`` in a loop.
- Comprehensions instead of ``append`` loops: they skip the method lookup and call that ``append`` costs per item.
"""

import re
import statistics
import subprocess  # nosec B404  # runs this Python with fixed arguments, never a shell
import sys
import timeit
from collections.abc import Callable, Mapping
from dataclasses import dataclass
lazy import colorsys

__all__ = ["Timing", "compare", "demo", "heat_colour", "import_cost", "is_loaded", "measure"]

_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")


def is_loaded(module: str) -> bool:
    """
    Whether a module has been imported in this process.

    :param module: The module name
    :returns: True when it is in ``sys.modules``
    """
    return module in sys.modules


def heat_colour(celsius: float) -> str:
    """
    Colour a fridge temperature from blue (cold) to red (warm). ``colorsys`` is lazily imported: it loads here.

    >>> heat_colour(0.0), heat_colour(15.0)
    ('#2f5cd0', '#d02f2f')

    :param celsius: The temperature, clamped to 0 to 15
    :returns: A hex colour
    """
    share = min(max(celsius, 0.0), 15.0) / 15.0
    red, green, blue = colorsys.hsv_to_rgb((1 - share) * 0.62, 0.775, 0.816)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in (red, green, blue))


@dataclass(frozen=True, slots=True)
class Timing:
    """
    How long one call takes.

    :param label: What was timed
    :param best: The best time per call, in seconds; the best is the least disturbed by other work on the machine
    :param median: The median time per call, in seconds
    :param calls: Calls per measurement
    """

    label: str
    best: float
    median: float
    calls: int

    def __str__(self) -> str:
        return f"{self.label}: {self.best * 1e6:,.2f} µs per call (median {self.median * 1e6:,.2f})"


def measure(label: str, func: Callable[[], object], repeat: int = 5, min_time: float = 0.2) -> Timing:
    """
    Time a call: double the number of calls until one measurement takes ``min_time``, then repeat it.

    :param label: What is being timed
    :param func: A call with no arguments
    :param repeat: How many measurements
    :param min_time: Seconds one measurement should take, so the clock's resolution does not matter
    :returns: The timing
    """
    timer = timeit.Timer(func)
    calls = 1
    while timer.timeit(calls) < min_time and calls < 10_000_000:
        calls *= 2
    runs = [total / calls for total in timer.repeat(repeat=repeat, number=calls)]
    return Timing(label, min(runs), statistics.median(runs), calls)


def compare(
    cases: Mapping[str, Callable[[], object]], repeat: int = 3, min_time: float = 0.2
) -> list[tuple[Timing, float]]:
    """
    Time several ways of doing the same thing, fastest first, each with how many times slower than the fastest.

    :param cases: Label to call
    :param repeat: Measurements per case
    :param min_time: Seconds per measurement
    :returns: Each timing with its ratio to the fastest
    """
    timings = sorted((measure(label, func, repeat, min_time) for label, func in cases.items()), key=lambda t: t.best)
    fastest = timings[0].best
    return [(timing, timing.best / fastest) for timing in timings]


def import_cost(module: str) -> float:
    """
    Measure how long importing a module takes in a fresh interpreter, with ``python -X importtime``.

    :param module: A module name such as ``json``
    :returns: The cumulative import time in milliseconds
    :raises ValueError: When the name is not a module name, or the import fails
    """
    if not _MODULE.fullmatch(module):
        raise ValueError(f"not a module name: {module!r}")
    result = subprocess.run(  # nosec B603  # sys.executable with fixed flags; the name was checked above
        [sys.executable, "-X", "importtime", "-c", f"import {module}"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ValueError(f"cannot import {module}: {result.stderr.strip().splitlines()[-1]}")
    for line in reversed(result.stderr.splitlines()):
        parts = [part.strip() for part in line.removeprefix("import time:").split("|")]
        if len(parts) == 3 and parts[2] == module:
            return int(parts[1]) / 1000
    raise ValueError(f"no import time reported for {module}")


def demo() -> None:
    """Show a lazy import loading on first use, then measure a few common choices and two import costs."""
    print(f"colorsys loaded before first use: {is_loaded('colorsys')}")
    print(f"walk in fridge at 3.5 °C is {heat_colour(3.5)}; colorsys loaded now: {is_loaded('colorsys')}")
    words = [f"dish {n}" for n in range(1_000)]

    def concat() -> str:
        text = ""
        for word in words:
            text += word + ","
        return text

    def loop() -> list[int]:
        out = []
        for word in words:
            out.append(len(word))
        return out

    for timing, ratio in compare({"str.join": lambda: ",".join(words), "+= in a loop": concat}, min_time=0.02):
        print(f"  {timing}  ({ratio:.1f}x)")
    for timing, ratio in compare(
        {"comprehension": lambda: [len(w) for w in words], "append loop": loop}, min_time=0.02
    ):
        print(f"  {timing}  ({ratio:.1f}x)")
    for module in ("json", "pydantic"):
        print(f"importing {module} costs {import_cost(module):.1f} ms in a fresh interpreter")
    print("so the CLI imports pydantic lazily: `mothersauce list` never pays for it")
