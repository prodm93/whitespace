"""Coverage gates for CI: line coverage, the tiered risk register, and unmeasured files.

Reads the JSON report of coverage.py, the ``protected.json`` counts written by the test
session (passed tests for each risk register item) and ``tests/risk_register.yaml``. Prints
one table, then each failed gate, and exits 1 when any gate fails:

- a ``.py`` file with at least one statement, in a folder that ``[tool.coverage.run]
  source`` of ``pyproject.toml`` measures, is missing from the coverage report;
- line coverage is under 80% of the statements;
- a critical or high item has no passed test;
- fewer than half of the medium items have a passed test;
- ``protected.json`` names an unknown item, or the register has a duplicate name or an
  unknown tier.

Low items are reported only.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

LINE_PERCENT = 80
TIERS = ("critical", "high", "medium", "low")


def _has_statements(path: Path) -> bool:
    body = ast.parse(path.read_text()).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return bool(body)


def _measured(root: Path) -> list[str]:
    """The folders that ``[tool.coverage.run] source`` of ``pyproject.toml`` measures."""
    settings = tomllib.loads((root / "pyproject.toml").read_text())
    return list(settings["tool"]["coverage"]["run"]["source"])


def _unmeasured(root: Path, reported: set[str]) -> list[str]:
    missing = []
    for top in _measured(root):
        for path in sorted((root / top).rglob("*.py")):
            name = path.relative_to(root).as_posix()
            if name not in reported and _has_statements(path):
                missing.append(name)
    return missing


def _register_faults(register: list[dict[str, Any]], passed: dict[str, int]) -> list[str]:
    names = [item["name"] for item in register]
    faults = [
        f"the register lists {name} twice" for name in sorted(set(names)) if names.count(name) > 1
    ]
    faults += [
        f"{item['name']} has the unknown tier {item['tier']}"
        for item in register
        if item["tier"] not in TIERS
    ]
    faults += [
        f"a passed test names the unknown item {name}" for name in sorted(set(passed) - set(names))
    ]
    return faults


def _tier_faults(by_tier: dict[str, tuple[list[str], list[str]]]) -> list[str]:
    faults = []
    for tier in ("critical", "high"):
        _, uncovered = by_tier[tier]
        faults += [f"the {tier} item {name} has no passed test" for name in uncovered]
    covered, uncovered = by_tier["medium"]
    total = len(covered) + len(uncovered)
    if len(covered) * 2 < total:
        faults.append(f"only {len(covered)} of {total} medium items have a passed test")
    return faults


def _table(covered: int, statements: int, by_tier: dict[str, tuple[list[str], list[str]]]) -> str:
    percent = 100 * covered / statements if statements else 100.0
    lines = [
        f"Line coverage: {percent:.2f}% ({covered} of {statements} statements;"
        f" gate {LINE_PERCENT}%)",
        f"{'Tier':<9} {'Items':>5} {'Covered':>7}  Not covered",
    ]
    for tier in TIERS:
        done, missing = by_tier[tier]
        lines.append(
            f"{tier:<9} {len(done) + len(missing):>5} {len(done):>7}  {', '.join(missing) or '-'}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--coverage", type=Path, default=Path("coverage.json"))
    parser.add_argument("--protected", type=Path, default=Path("protected.json"))
    parser.add_argument("--register", type=Path, default=Path("tests/risk_register.yaml"))
    args = parser.parse_args(argv)

    report = json.loads(args.coverage.read_text())
    passed: dict[str, int] = json.loads(args.protected.read_text())
    register: list[dict[str, Any]] = yaml.safe_load(args.register.read_text())
    covered = report["totals"]["covered_lines"]
    statements = report["totals"]["num_statements"]

    by_tier: dict[str, tuple[list[str], list[str]]] = {tier: ([], []) for tier in TIERS}
    for item in register:
        if item["tier"] in by_tier:
            done, missing = by_tier[item["tier"]]
            (done if passed.get(item["name"], 0) > 0 else missing).append(item["name"])

    faults = [
        f"not in the coverage report: {name}"
        for name in _unmeasured(args.root, set(report["files"]))
    ]
    if covered * 100 < LINE_PERCENT * statements:
        faults.append(f"line coverage is under {LINE_PERCENT}%")
    faults += _tier_faults(by_tier) + _register_faults(register, passed)

    print(_table(covered, statements, by_tier))
    for fault in faults:
        print(f"FAIL: {fault}")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
