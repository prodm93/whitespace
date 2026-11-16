"""Manual two-tenant check of the SaaS knowledge graph. Writes nothing to the graph.

Run on a machine whose ``.env`` holds the SaaS Neo4j credentials:

- ``python scripts/tenancy_check.py read <tenant ID> <query>`` reads the graph as one tenant
  through the app's own graph tools and prints the raw output of ``search_graph``,
  ``list_entities`` and ``inspect_entity`` (the query is also the entity name).
- ``python scripts/tenancy_check.py lifecycle <tenant A> <tenant B>`` drives the pipeline
  function's own run lifecycle (``_runtime.py``, loaded by file path) through: a run of A,
  a run of B, a run of A opened with no finish (a run that died), each reading both marker
  words through the run pipeline; first with the kept clients, then with
  ``PIPELINE_REUSE=invocation``. After each open it prints the identity of the kept clients
  and the namespace of the run pipeline. For this mode set ``MODE=byok`` and leave
  ``SESSIONS_TABLE`` unset, so that no AWS credentials are needed. This mode takes its
  credentials from the local ``.env``, not from the stored secret of the pipeline function.

Each read in lifecycle mode makes one planner model call and embedding calls.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

from whitespace.agents._graph_actions import GraphActions
from whitespace.config import Config
from whitespace.orchestration._wiring import build_shared
from whitespace.tenant import require_tenant_id
from whitespace.tools.graph_tools import GraphTools

MARKERS = ("ZEBRAQUARTZ", "MOONLATHE")
_PIPELINE_FUNCTION = (
    Path(__file__).resolve().parents[1] / "deploy" / "aws" / "lambda" / "pipeline_orchestrator"
)


async def read_as(tenant: str, query: str) -> None:
    """Print what the three graph tools return for ``query`` in ``tenant``'s namespace."""
    owner = require_tenant_id(tenant)
    config = Config()
    shared = build_shared(config)
    try:
        await shared.initialise()
        tenant_config = config.model_copy(update={"graphiti_namespace": owner})
        actions = GraphActions(tenant_config, GraphTools(shared.graphiti, shared.neo4j))
        calls = [
            ("search_graph", {"query": query}),
            ("list_entities", {"query": query}),
            ("inspect_entity", {"entity_name": query}),
        ]
        for name, arguments in calls:
            print(f"=== {name}({arguments}) as {owner}")
            print(await actions.dispatch(name, arguments))
    finally:
        await shared.close()


def _load_runtime() -> ModuleType:
    """Load the pipeline function's ``_runtime.py`` with its sibling modules importable."""
    sys.path.insert(0, str(_PIPELINE_FUNCTION))
    spec = importlib.util.spec_from_file_location("_runtime", _PIPELINE_FUNCTION / "_runtime.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {_PIPELINE_FUNCTION / '_runtime.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_runtime"] = module
    spec.loader.exec_module(module)

    async def load_local_config() -> Config:
        return Config()

    module.load_config = load_local_config
    return module


async def _read(runtime: ModuleType, marker: str) -> str:
    """Read one marker through the run pipeline that is open when the read starts."""
    answer: str = await runtime.get_pipeline()._context_agent.run(marker)
    return answer


async def _opened(runtime: ModuleType) -> tuple[int, str]:
    """The identity of the kept clients and the namespace of the run pipeline that is open."""
    namespace: str = runtime.get_pipeline()._config.graphiti_namespace
    return id(runtime._shared), namespace


def _open_and_read(runtime: ModuleType, tenant: str, label: str) -> None:
    runtime.run(runtime.open_run(tenant))
    shared_id, namespace = runtime.run(_opened(runtime))
    print(f"=== {label}: opened {tenant}; id(_shared)={shared_id}; namespace={namespace}")
    for marker in MARKERS:
        answer = runtime.run(_read(runtime, marker))
        print(f"--- {label}: read {marker} as {tenant}\n{answer}\n")


def _sequence(runtime: ModuleType, tenant_a: str, tenant_b: str, reuse: str) -> None:
    os.environ["PIPELINE_REUSE"] = reuse
    _open_and_read(runtime, tenant_a, f"{reuse} a")
    runtime.finish_run()
    _open_and_read(runtime, tenant_b, f"{reuse} b")
    _open_and_read(runtime, tenant_a, f"{reuse} c, no finish before it")
    runtime.finish_run()


def lifecycle(tenant_a: str, tenant_b: str) -> None:
    """Drive the run lifecycle for two tenants, with kept clients and then without."""
    runtime = _load_runtime()
    try:
        _sequence(runtime, tenant_a, tenant_b, "container")
        _sequence(runtime, tenant_a, tenant_b, "invocation")
    finally:
        os.environ["PIPELINE_REUSE"] = "invocation"
        runtime.finish_run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    read = modes.add_parser("read", help="read the graph as one tenant")
    read.add_argument("tenant")
    read.add_argument("query")
    runs = modes.add_parser("lifecycle", help="drive the run lifecycle for two tenants")
    runs.add_argument("tenant_a")
    runs.add_argument("tenant_b")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "read":
        asyncio.run(read_as(args.tenant, args.query))
    else:
        lifecycle(args.tenant_a, args.tenant_b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
