"""Source rules that keep every Graphiti call inside one tenant's group.

A Graphiti search passes exactly one group, every episode write passes a group, no read or
delete by ID is called, and these calls live only in the three graph files. Limit: the
checker does not follow aliases, so ``g = self._graphiti.graphiti; g.search(...)`` is not
seen by the search rule or the file rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "whitespace"
_BY_ID = {
    "get_by_uuid",
    "get_by_uuids",
    "delete",
    "delete_by_uuids",
    "delete_by_group_id",
    "remove_episode",
    "clear_data",
}
_SEARCHES = {"search", "search_"}
_WRITES = {"add_episode", "add_episode_bulk"}
_GRAPH_FILES = {"tools/graph/edges.py", "tools/graph/nodes.py", "agents/graph_agent.py"}


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _one_group(value: ast.expr | None) -> bool:
    return (
        isinstance(value, ast.List)
        and len(value.elts) == 1
        and not isinstance(value.elts[0], ast.Constant)
    )


def find_violations(source: str, path: str) -> list[str]:
    """Return one message for each call in ``source`` that breaks a rule; ``path`` is
    relative to ``src/whitespace``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name, where = node.func.attr, f"{path}:{node.lineno}"
        receiver = node.func.value
        search = (
            name in _SEARCHES
            and isinstance(receiver, ast.Attribute)
            and receiver.attr == "graphiti"
        )
        if name in _BY_ID:
            found.append(f"{where}: {name}() ignores the group")
        if search and not _one_group(_keyword(node, "group_ids")):
            found.append(f"{where}: {name}() must pass group_ids=[<one group>]")
        group = _keyword(node, "group_id")
        if name in _WRITES and (group is None or isinstance(group, ast.Constant)):
            found.append(f"{where}: {name}() must pass group_id=<the run's group>")
        if (search or name in _WRITES) and path not in _GRAPH_FILES:
            found.append(f"{where}: {name}() is only called in the three graph files")
    return found


def _body(call: str) -> str:
    return f"async def f(self, group_id, groups, a, b, driver, uuid):\n    await {call}\n"


@pytest.mark.parametrize(
    "path", [p.relative_to(_SRC).as_posix() for p in sorted(_SRC.rglob("*.py"))]
)
@pytest.mark.protects("graph-calls-one-group-only")
def test_the_source_tree_keeps_every_graph_call_in_one_group(path: str) -> None:
    assert find_violations((_SRC / path).read_text(), path) == []


@pytest.mark.parametrize(
    ("call", "path"),
    [
        ("self._graphiti.graphiti.search(query='q')", "tools/graph/edges.py"),
        ("self._graphiti.graphiti.search(query='q', group_ids=None)", "tools/graph/edges.py"),
        ("self._graphiti.graphiti.search(query='q', group_ids=[])", "tools/graph/edges.py"),
        ("self._graphiti.graphiti.search(query='q', group_ids=[a, b])", "tools/graph/edges.py"),
        ("self._graphiti.graphiti.search_(query='q', group_ids=groups)", "tools/graph/nodes.py"),
        ("self._graphiti.graphiti.add_episode(name='n')", "agents/graph_agent.py"),
        ("self._graphiti.graphiti.add_episode(name='n', group_id=None)", "agents/graph_agent.py"),
        ("node.delete(driver)", "tools/graph/edges.py"),
        ("EntityNode.get_by_uuid(driver, uuid)", "tools/graph/edges.py"),
        ("EntityNode.delete_by_group_id(driver, group_id)", "tools/graph/edges.py"),
        (
            "self._graphiti.graphiti.search(query='q', group_ids=[group_id])",
            "agents/context_agent.py",
        ),
    ],
)
@pytest.mark.protects("graph-calls-one-group-only")
def test_the_checker_rejects_a_call_that_can_cross_groups(call: str, path: str) -> None:
    assert len(find_violations(_body(call), path)) == 1


@pytest.mark.parametrize(
    ("call", "path"),
    [
        ("self._graphiti.graphiti.search(query='q', group_ids=[group_id])", "tools/graph/edges.py"),
        (
            "self._graphiti.graphiti.search_(query='q', group_ids=[group_id])",
            "tools/graph/nodes.py",
        ),
        (
            "self._graphiti.graphiti.add_episode(name='n', group_id=group_id)",
            "agents/graph_agent.py",
        ),
    ],
)
@pytest.mark.protects("graph-calls-one-group-only")
def test_the_checker_accepts_a_call_in_one_group(call: str, path: str) -> None:
    assert find_violations(_body(call), path) == []
