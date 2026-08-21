"""Shared test doubles for SaaS pipeline orchestrator tests."""

from __future__ import annotations

import sys
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

# --- SDK stub (must precede handler imports) ---

_sdk = types.ModuleType("aws_durable_execution_sdk_python")


@dataclass
class _FakeStepContext:
    name: str = ""


@dataclass
class FakeDurableContext:
    """Records step calls; raises on wait_for_callback."""

    _journal: dict[str, Any] = field(default_factory=dict)
    step_calls: list[str] = field(default_factory=list)

    def step(self, fn: Any, *, name: str) -> Any:
        self.step_calls.append(name)
        if name in self._journal:
            return self._journal[name]
        result = fn(_FakeStepContext(name=name))
        self._journal[name] = result
        return result

    def wait_for_callback(self, *_a: Any, **_kw: Any) -> None:
        raise AssertionError("wait_for_callback must not be called")


_sdk.DurableContext = FakeDurableContext
_sdk.durable_execution = lambda fn: fn
sys.modules["aws_durable_execution_sdk_python"] = _sdk

_HANDLER_DIR = str(
    Path(__file__).parent.parent / "deploy" / "aws" / "lambda" / "pipeline_orchestrator"
)
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)


# --- Test doubles ---


def _need(title: str) -> UnmetNeed:
    return UnmetNeed(title=title, description="d", current_state="c", why_unmet="w")


def _proposal(title: str) -> IdeationProposal:
    return IdeationProposal(
        title=title,
        problem_statement="p",
        technical_approach="t",
        why_this_person="y",
        differentiation_from_prior_art="d",
        limitations="l",
    )


def _profile() -> ProfessionalProfile:
    return ProfessionalProfile(hard_skills=["Python"], domain_knowledge=["patents"])


class FakePipeline:
    def __init__(
        self,
        needs: list[UnmetNeed] | None = None,
        proposals: list[IdeationProposal] | None = None,
    ) -> None:
        self.needs = needs or [_need("Gap A")]
        self.proposals = proposals or [_proposal("Idea X")]
        self.analyse_calls = 0
        self.ideate_calls = 0
        self.router = FakeRouter([])

    async def extract_profile(self, _paths: list[str]) -> ProfessionalProfile:
        return _profile()

    async def analyse_gaps(self, *_a: Any, **_kw: Any) -> list[UnmetNeed]:
        self.analyse_calls += 1
        return self.needs

    async def ideate(self, *_a: Any, **_kw: Any) -> list[IdeationProposal]:
        self.ideate_calls += 1
        return self.proposals

    async def query(self, question: str) -> str:
        return f"answer: {question}"


class FakeRouter:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._resp = responses
        self._i = 0

    async def call(self, **_kw: Any) -> dict[str, Any]:
        if not self._resp:
            return {
                "content": "done",
                "tool_calls": [],
                "stop_reason": "end",
            }
        r = self._resp[min(self._i, len(self._resp) - 1)]
        self._i += 1
        return r


class FakeStore:
    def __init__(self, gap_run: Any = None) -> None:
        self._gap_run = gap_run

    async def get_latest_gap_run(self) -> Any:
        return self._gap_run


def _tc(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"id": "t0", "name": name, "arguments": args or {}}],
        "stop_reason": "tool_use",
    }


_DONE: dict[str, Any] = {
    "content": "ok",
    "tool_calls": [],
    "stop_reason": "end",
}


def _handler_boto3(*, with_reservation: bool = False) -> MagicMock:
    fb = MagicMock()
    if with_reservation:
        fb.resource.return_value.Table.return_value.get_item.return_value = {
            "Item": {
                "reservation_status": "pending",
                "reservation_expires_at": int(time.time()) + 3600,
                "user_id": "u1",
            }
        }
    return fb


def _evt(job_id: str, intent: str, **kw: Any) -> dict:
    return {
        "job_id": job_id,
        "payload": {
            "intent": intent,
            "user_id": kw.get("user_id", ""),
            "selected_titles": list(kw.get("selected_titles", [])),
            "fresh_start": bool(kw.get("fresh_start", False)),
            "profile_paths": list(kw.get("profile_paths", [])),
            "doc_paths": list(kw.get("doc_paths", [])),
        },
    }
