"""The manual two-tenant check script: its two modes, its usage message, and its reads."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from _loop_helpers import Stubborn, tick
from _module_loading import load_module
from _runtime_helpers import FakeShared, record_waits, use_factory, use_recorder
from neo4j.exceptions import ServiceUnavailable

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tenancy_check.py"


def _script() -> Any:
    module = load_module("tenancy_check", _SCRIPT)
    return module


def test_both_modes_exist_and_a_missing_argument_prints_the_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = _script().build_parser()

    read = parser.parse_args(["read", "user_a", "ZEBRAQUARTZ"])
    lifecycle = parser.parse_args(["lifecycle", "user_a", "user_b"])
    with pytest.raises(SystemExit) as missing:
        _script().main(["read", "user_a"])

    assert (read.mode, read.tenant, read.query) == ("read", "user_a", "ZEBRAQUARTZ")
    assert (lifecycle.mode, lifecycle.tenant_a, lifecycle.tenant_b) == (
        "lifecycle",
        "user_a",
        "user_b",
    )
    assert missing.value.code == 2
    assert "usage:" in capsys.readouterr().err


class _ReadPipeline:
    """A run pipeline whose context agent records which pipeline served each read.

    With ``leave_work``, the first read of the test leaves a task that ignores cancellation.
    """

    def __init__(
        self, index: int, shared: Any, config: Any, reads: list[Any], leave_work: bool
    ) -> None:
        self._config = config
        self._context_agent = self
        self._index = index
        self._shared = shared
        self._reads = reads
        self._leave_work = leave_work
        self.leftover = Stubborn()

    async def run(self, marker: str) -> str:
        self._reads.append((self._index, marker, "close" in self._shared.calls))
        if self._leave_work and not self._reads[:-1]:
            asyncio.ensure_future(self.leftover.run())
            await tick()
        return f"answer {marker}"


class _StubbornCandidate(FakeShared):
    """A set of kept clients that starts work which ignores cancellation, then fails its check."""

    def __init__(self) -> None:
        super().__init__(check_errors=[ServiceUnavailable("unreachable")])
        self.leftover = Stubborn()

    async def initialise(self) -> None:
        asyncio.ensure_future(self.leftover.run())
        await super().initialise()


def _use_read_pipelines(
    monkeypatch: Any, runtime: Any, *, leave_work: bool
) -> tuple[list[Any], list[_ReadPipeline]]:
    """Make the runtime build a new ``_ReadPipeline`` for each run; return the reads and builds."""
    import _teardown

    monkeypatch.setattr(_teardown, "CANCEL_WAIT", 0.05)
    reads: list[Any] = []
    built: list[_ReadPipeline] = []

    def from_shared(shared: Any, config: Any, **_kwargs: Any) -> _ReadPipeline:
        built.append(_ReadPipeline(len(built), shared, config, reads, leave_work))
        return built[-1]

    monkeypatch.setattr(runtime, "Pipeline", types.SimpleNamespace(from_shared=from_shared))
    return reads, built


def test_a_read_after_a_retirement_uses_the_reopened_run_pipeline(
    monkeypatch: Any, runtime: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    use_factory(monkeypatch, runtime)
    reads, built = _use_read_pipelines(monkeypatch, runtime, leave_work=True)

    _script()._open_and_read(runtime, "user_a", "a")

    assert reads == [(0, "ZEBRAQUARTZ", False), (1, "MOONLATHE", False)]
    assert [pipeline._config.graphiti_namespace for pipeline in built] == ["user_a", "user_a"]
    assert "answer MOONLATHE" in capsys.readouterr().out


def test_a_retirement_while_the_run_opens_leaves_the_banner_and_reads_working(
    monkeypatch: Any, runtime: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch, runtime, lambda n: _StubbornCandidate() if n == 0 else FakeShared()
    )
    reads, built = _use_read_pipelines(monkeypatch, runtime, leave_work=False)

    _script()._open_and_read(runtime, "user_a", "a")

    assert len(factory.built) == 3
    assert reads == [(1, "ZEBRAQUARTZ", False), (1, "MOONLATHE", False)]
    assert [pipeline._config.graphiti_namespace for pipeline in built] == ["user_a", "user_a"]
    out = capsys.readouterr().out
    assert f"id(_shared)={id(factory.built[2])}; namespace=user_a" in out
    assert "answer MOONLATHE" in out


def test_the_lifecycle_runtime_opens_a_run_from_the_local_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIPELINE_SECRET_ARN", raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "local-password")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "_runtime", raising=False)
    runtime = _script()._load_runtime()
    use_factory(monkeypatch, runtime)
    recorder = use_recorder(monkeypatch, runtime)

    try:
        runtime.run(runtime.open_run("user_a"))
    finally:
        monkeypatch.setenv("PIPELINE_REUSE", "invocation")
        runtime.finish_run()

    assert recorder.calls[0][1].neo4j_password == "local-password"
    assert recorder.calls[0][1].graphiti_namespace == "user_a"
