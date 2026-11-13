"""
Measure how fast the command starts, and prove ``list`` never imports the heavy modules.

    python scripts/bench_startup.py

Each command runs 20 times in a fresh interpreter; the best time is reported, because the best run is the one least
disturbed by everything else the machine was doing. ``python -c pass`` is the floor: the interpreter's own start up.
"""

import subprocess  # nosec B404  # runs this Python with fixed arguments, never a shell
import sys
import time

RUNS = 20
CASES = {
    "python -c pass": ["-c", "pass"],
    "mothersauce --version": ["-m", "mothersauce", "--version"],
    "mothersauce list": ["-m", "mothersauce", "list"],
    "mothersauce search retry": ["-m", "mothersauce", "search", "retry"],
}


def best_of(args: list[str]) -> float:
    """
    Time a command in a fresh interpreter, best of several runs.

    :param args: Arguments after the interpreter
    :returns: The best time in milliseconds
    """
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        subprocess.run([sys.executable, *args], capture_output=True, check=True)  # nosec B603  # fixed arguments
        times.append((time.perf_counter() - start) * 1000)
    return min(times)


def heavy_imports() -> list[str]:
    """
    List the heavy modules ``mothersauce list`` imports. The answer should be none.

    :returns: Module names
    """
    result = subprocess.run(  # nosec B603  # fixed arguments
        [sys.executable, "-X", "importtime", "-m", "mothersauce", "list"], capture_output=True, text=True, check=True
    )
    names = [line.rsplit("|", 1)[-1].strip() for line in result.stderr.splitlines() if "|" in line]
    return [n for n in names if n.split(".")[0] in {"pydantic", "pydantic_core", "sqlite3", "asyncio", "decimal"}]


def main() -> int:
    """
    Print the table and fail when ``list`` pulls in a heavy module.

    :returns: Exit code
    """
    for label, args in CASES.items():
        print(f"{label:<28} {best_of(args):6.1f} ms")
    heavy = heavy_imports()
    print(f"heavy modules imported by `mothersauce list`: {', '.join(heavy) or 'none'}")
    return 1 if heavy else 0


if __name__ == "__main__":
    sys.exit(main())
