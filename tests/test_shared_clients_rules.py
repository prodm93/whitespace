"""Source rules that keep tenant data out of the clients kept between runs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "whitespace"
_SHARED_MODULE = _SRC / "orchestration" / "_shared_clients.py"
_KEPT_CLASSES = {
    "Neo4jClient": _SRC / "graph" / "neo4j_client.py",
    "GraphitiClient": _SRC / "graph" / "graphiti_client.py",
    "ProviderFactory": _SRC / "models" / "providers.py",
}
_FORBIDDEN_IMPORTS = ("whitespace.store", "whitespace.agents", "whitespace.tenant")
_KEPT_FIELDS = ["neo4j", "graphiti", "provider_factory"]
_TENANT_NAMES = {"user_id", "owner", "tenant", "namespace", "group_id", "session_store"}


def import_violations(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            continue
        for module in modules:
            if module.startswith(_FORBIDDEN_IMPORTS):
                found.append(f"imports {module}")
    return found


def field_violations(source: str) -> list[str]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "SharedClients":
            fields = [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
            if fields != _KEPT_FIELDS:
                return [f"SharedClients fields {fields}: a new field needs a tenancy review"]
            return []
    return ["SharedClients not found"]


def init_violations(source: str, class_name: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
                found += [
                    f"{class_name}.__init__ parameter {arg.arg}"
                    for arg in stmt.args.args + stmt.args.kwonlyargs
                    if arg.arg in _TENANT_NAMES
                ]
                found += [
                    f"{class_name}.__init__ attribute {target.attr}"
                    for sub in ast.walk(stmt)
                    if isinstance(sub, ast.Assign | ast.AnnAssign)
                    for target in (sub.targets if isinstance(sub, ast.Assign) else [sub.target])
                    if isinstance(target, ast.Attribute)
                    and target.attr.lstrip("_") in _TENANT_NAMES
                ]
    return found


def namespace_violations(source: str) -> list[str]:
    return ["mentions graphiti_namespace"] if "graphiti_namespace" in source else []


def test_shared_module_imports_no_tenant_bound_code() -> None:
    assert import_violations(_SHARED_MODULE.read_text()) == []


def test_shared_clients_has_exactly_the_three_kept_fields() -> None:
    assert field_violations(_SHARED_MODULE.read_text()) == []


@pytest.mark.parametrize("class_name", sorted(_KEPT_CLASSES))
def test_kept_class_takes_and_keeps_no_tenant_data(class_name: str) -> None:
    assert init_violations(_KEPT_CLASSES[class_name].read_text(), class_name) == []


@pytest.mark.parametrize("class_name", sorted(_KEPT_CLASSES))
def test_kept_class_source_never_reads_the_namespace(class_name: str) -> None:
    assert namespace_violations(_KEPT_CLASSES[class_name].read_text()) == []


def test_checker_rejects_a_tenant_bound_import() -> None:
    assert import_violations("from whitespace.store.base import SessionStore\n")
    assert import_violations("import whitespace.agents.graph_agent\n")
    assert import_violations("from whitespace.tenant import require_tenant_id\n")


def test_checker_rejects_a_fourth_field() -> None:
    source = (
        "class SharedClients:\n"
        "    neo4j: int\n    graphiti: int\n    provider_factory: int\n    cache: dict\n"
    )
    assert field_violations(source) == [
        "SharedClients fields ['neo4j', 'graphiti', 'provider_factory', 'cache']: "
        "a new field needs a tenancy review"
    ]


def test_checker_rejects_tenant_data_in_a_kept_constructor() -> None:
    as_parameter = "class Neo4jClient:\n    def __init__(self, config, user_id):\n        pass\n"
    as_attribute = "class Neo4jClient:\n    def __init__(self, config):\n        self._owner = 1\n"
    assert init_violations(as_parameter, "Neo4jClient") == [
        "Neo4jClient.__init__ parameter user_id"
    ]
    assert init_violations(as_attribute, "Neo4jClient") == ["Neo4jClient.__init__ attribute _owner"]


def test_checker_rejects_a_namespace_read() -> None:
    assert namespace_violations("x = self._config.graphiti_namespace\n")
