import subprocess
import sys

import pytest

from mothersauce.recipes.performance import compare, demo, heat_colour, import_cost, is_loaded, measure


def test_lazy_import_loads_on_first_use() -> None:
    code = (
        "import sys\n"
        "from mothersauce.recipes import performance\n"
        "print('colorsys' in sys.modules)\n"
        "performance.heat_colour(4.0)\n"
        "print('colorsys' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["False", "True"]


@pytest.mark.parametrize(
    ("celsius", "colour"), [(-5.0, "#2f5cd0"), (0.0, "#2f5cd0"), (15.0, "#d02f2f"), (99.0, "#d02f2f")]
)
def test_heat_colour_is_clamped(celsius: float, colour: str) -> None:
    assert heat_colour(celsius) == colour


def test_is_loaded() -> None:
    assert is_loaded("sys")
    assert not is_loaded("surely_not_a_module")


def test_measure_reports_per_call_times() -> None:
    timing = measure("sum", lambda: sum(range(100)), repeat=2, min_time=0.005)
    assert timing.label == "sum" and timing.calls >= 1
    assert 0 < timing.best <= timing.median
    assert str(timing).startswith("sum: ")


def test_compare_orders_fastest_first() -> None:
    results = compare({"slow": lambda: sum(range(20_000)), "fast": lambda: None}, repeat=2, min_time=0.005)
    assert [t.label for t, _ in results] == ["fast", "slow"]
    assert results[0][1] == 1.0 and results[1][1] > 1.0


def test_import_cost() -> None:
    assert import_cost("json") > 0


@pytest.mark.parametrize("name", ["json; import os", "1abc", ""])
def test_import_cost_checks_the_name(name: str) -> None:
    with pytest.raises(ValueError, match="not a module name"):
        import_cost(name)


def test_import_cost_reports_a_failed_import() -> None:
    with pytest.raises(ValueError, match="cannot import"):
        import_cost("surely_not_a_module")


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "importing pydantic costs" in out and "str.join" in out
