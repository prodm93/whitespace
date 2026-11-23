from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store._identities import finding_identity, identity_digest
from whitespace.store.base import GapRun, IdeaRun

DISCARD_KINDS = ("gap", "idea")


def gap_run_pk(owner: str) -> str:
    return f"USER#{owner}#GAPRUN"


def idea_run_pk(owner: str) -> str:
    return f"USER#{owner}#IDEARUN"


def findings_pk(owner: str) -> str:
    return f"USER#{owner}#FINDINGS"


def discard_pk(owner: str, kind: str) -> str:
    return f"USER#{owner}#DISCARD#{kind}"


def gap_run_to_item(owner: str, run: GapRun) -> dict[str, Any]:
    return {
        "pk": gap_run_pk(owner),
        "sk": f"{run.timestamp.isoformat()}#{run.run_id}",
        "run_id": run.run_id,
        "payload": run.model_dump_json(),
    }


def item_to_gap_run(item: dict[str, Any]) -> GapRun:
    return GapRun.model_validate_json(item["payload"])


def idea_run_to_item(owner: str, run: IdeaRun) -> dict[str, Any]:
    return {
        "pk": idea_run_pk(owner),
        "sk": f"{run.timestamp.isoformat()}#{run.run_id}",
        "run_id": run.run_id,
        "gap_run_id": run.gap_run_id,
        "payload": run.model_dump_json(),
    }


def item_to_idea_run(item: dict[str, Any]) -> IdeaRun:
    return IdeaRun.model_validate_json(item["payload"])


def finding_to_item(owner: str, run_id: str, finding: RawFinding) -> dict[str, Any]:
    return {
        "pk": findings_pk(owner),
        "sk": f"{run_id}#{identity_digest(finding_identity(finding))}",
        "run_id": run_id,
        "found_at": finding.found_at.isoformat(),
        "payload": finding.model_dump_json(),
    }


def item_to_finding(item: dict[str, Any]) -> RawFinding:
    return RawFinding.model_validate_json(item["payload"])


def discard_to_item(owner: str, run_id: str, kind: str, entry: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "pk": discard_pk(owner, kind),
        "sk": f"{now}#{uuid.uuid4()}",
        "run_id": run_id,
        "kind": kind,
        "title": entry.get("title", ""),
        "description": entry.get("description", ""),
        "reason": entry.get("reason", ""),
        "domain": entry.get("domain", ""),
    }


def item_to_discard(item: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": item["kind"],
        "title": item["title"],
        "description": item["description"],
        "reason": item["reason"],
        "domain": item.get("domain", ""),
    }


def needs_from_gap_run_item(item: dict[str, Any]) -> list[UnmetNeed]:
    return item_to_gap_run(item).needs


def proposals_from_idea_run_item(item: dict[str, Any]) -> list[IdeationProposal]:
    return item_to_idea_run(item).proposals
