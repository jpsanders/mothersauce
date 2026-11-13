import shlex
from typing import Any

import pytest
from pytest_bdd import parsers, scenarios, then, when

from mothersauce.cli import main

scenarios("menu.feature")


@pytest.fixture
def result() -> dict[str, Any]:
    """
    Hold the last command's exit status and output.

    :returns: An empty dict the steps fill in
    """
    return {}


@when(parsers.parse("I run mothersauce {arguments}"))
def run_command(result: dict[str, Any], arguments: str, capsys: pytest.CaptureFixture[str]) -> None:
    result["code"] = main(shlex.split(arguments))
    result["out"], result["err"] = capsys.readouterr()


@then(parsers.parse("the first recipe is {recipe}"))
def first_recipe(result: dict[str, Any], recipe: str) -> None:
    assert result["out"].splitlines()[1].split()[0] == recipe


@then(parsers.parse("the exit status is {code:d}"))
def exit_status(result: dict[str, Any], code: int) -> None:
    assert result["code"] == code


@then(parsers.parse('the output starts with "{text}"'))
def output_starts(result: dict[str, Any], text: str) -> None:
    assert result["out"].startswith(text)


@then(parsers.parse('the output contains "{text}"'))
def output_contains(result: dict[str, Any], text: str) -> None:
    assert text in result["out"]


@then(parsers.parse('the error suggests "{recipe}"'))
def error_suggests(result: dict[str, Any], recipe: str) -> None:
    assert f"did you mean {recipe}" in result["err"]
