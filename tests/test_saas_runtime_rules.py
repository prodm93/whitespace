"""Source rules for the pipeline function: no reuse by tenant, no parallel work."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_FUNCTION_DIR = _ROOT / "deploy" / "aws" / "lambda" / "pipeline_orchestrator"
_TENANT_WORDS = ("user", "owner", "tenant")
_PARALLEL_FORMS = (
    "context.parallel",
    "context.map",
    "ThreadPoolExecutor",
    "asyncio.run(",
    "threading.Thread",
)


def _names_in(node: ast.AST) -> list[str]:
    return [
        part.id if isinstance(part, ast.Name) else part.attr
        for part in ast.walk(node)
        if isinstance(part, ast.Name | ast.Attribute)
    ]


def tenant_comparisons(source: str) -> list[str]:
    """Each ``==`` or ``!=`` that has a tenant-like name on either side."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
            continue
        names = [n for n in _names_in(node) if any(w in n.lower() for w in _TENANT_WORDS)]
        if names:
            found.append(ast.unparse(node))
    return found


@pytest.mark.protects("run-pipeline-never-reused")
def test_the_runtime_never_compares_tenant_ids() -> None:
    source = (_FUNCTION_DIR / "_runtime.py").read_text()

    assert tenant_comparisons(source) == []


def test_the_comparison_rule_rejects_a_reuse_by_tenant() -> None:
    sample = "if _owner == user_id:\n    pass\nif cached.tenant != new_tenant:\n    pass\n"

    assert len(tenant_comparisons(sample)) == 2


def test_no_module_of_the_pipeline_function_runs_work_in_parallel() -> None:
    offenders = [
        f"{path.name}: {form}"
        for path in sorted(_FUNCTION_DIR.glob("*.py"))
        for form in _PARALLEL_FORMS
        if form in path.read_text()
    ]

    assert offenders == []
