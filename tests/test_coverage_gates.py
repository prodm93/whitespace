"""The coverage gate: line coverage, the tiered risk register, and files missing from the report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _module_loading import load_module

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "coverage_gates.py"


def _gates() -> Any:
    module = load_module("coverage_gates", _SCRIPT)
    return module


_REGISTER = [
    {"name": "c1", "tier": "critical", "protects": "x"},
    {"name": "h1", "tier": "high", "protects": "x"},
    {"name": "m1", "tier": "medium", "protects": "x"},
    {"name": "m2", "tier": "medium", "protects": "x"},
    {"name": "l1", "tier": "low", "protects": "x"},
]
_ALL_FILES = ["src/whitespace/a.py", "deploy/aws/lambda/f/handler.py"]


def _run(
    tmp_path: Path,
    *,
    covered: int = 80,
    statements: int = 100,
    passed: dict[str, int] | None = None,
    register: list[dict[str, str]] | None = None,
    reported: list[str] | None = None,
) -> int:
    for name in _ALL_FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('"""A module."""\n\nVALUE = 1\n')
    (tmp_path / "src" / "whitespace" / "empty.py").write_text('"""Only a docstring."""\n')
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["src/whitespace", "deploy/aws/lambda"]\n'
    )
    files = {name: {"summary": {}} for name in (_ALL_FILES if reported is None else reported)}
    coverage = {"totals": {"covered_lines": covered, "num_statements": statements}, "files": files}
    (tmp_path / "coverage.json").write_text(json.dumps(coverage))
    (tmp_path / "protected.json").write_text(json.dumps(passed or {"c1": 1, "h1": 2, "m1": 1}))
    (tmp_path / "register.yaml").write_text(json.dumps(register or _REGISTER))
    return _gates().main(
        [
            "--root",
            str(tmp_path),
            "--coverage",
            str(tmp_path / "coverage.json"),
            "--protected",
            str(tmp_path / "protected.json"),
            "--register",
            str(tmp_path / "register.yaml"),
        ]
    )


@pytest.mark.protects("coverage-gate-reports-table")
def test_all_gates_met_passes_and_prints_the_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path) == 0
    out = capsys.readouterr().out
    assert "Line coverage: 80.00%" in out
    assert "medium" in out and "m2" in out


@pytest.mark.parametrize(("covered", "statements", "result"), [(7999, 10000, 1), (80, 100, 0)])
def test_line_coverage_must_reach_eighty_percent(
    tmp_path: Path, covered: int, statements: int, result: int
) -> None:
    assert _run(tmp_path, covered=covered, statements=statements) == result


def test_a_critical_item_with_no_passed_test_fails(tmp_path: Path) -> None:
    assert _run(tmp_path, passed={"h1": 1, "m1": 1}) == 1


def test_one_of_three_medium_items_fails_and_two_of_four_passes(tmp_path: Path) -> None:
    three = [*_REGISTER, {"name": "m3", "tier": "medium", "protects": "x"}]
    four = [*three, {"name": "m4", "tier": "medium", "protects": "x"}]

    assert _run(tmp_path, register=three, passed={"c1": 1, "h1": 1, "m1": 1}) == 1
    assert _run(tmp_path, register=four, passed={"c1": 1, "h1": 1, "m1": 1, "m2": 1}) == 0


def test_a_passed_test_for_an_unknown_item_fails(tmp_path: Path) -> None:
    assert _run(tmp_path, passed={"c1": 1, "h1": 1, "m1": 1, "nope": 1}) == 1


@pytest.mark.parametrize(
    "register",
    [
        [*_REGISTER, {"name": "c1", "tier": "critical", "protects": "x"}],
        [*_REGISTER, {"name": "z1", "tier": "severe", "protects": "x"}],
    ],
)
def test_a_duplicate_name_or_an_unknown_tier_fails(
    tmp_path: Path, register: list[dict[str, str]]
) -> None:
    assert _run(tmp_path, register=register) == 1


def test_a_file_with_statements_missing_from_the_report_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, reported=["src/whitespace/a.py"]) == 1
    assert "deploy/aws/lambda/f/handler.py" in capsys.readouterr().out
