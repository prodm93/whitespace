"""Shared mechanics for council critics: schema building, parsing, invocation."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from whitespace.agents.council._helpers import format_pool, format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.critique import CandidateLike, CriticAssessment, CriticReport
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_VERDICTS = ["keep", "kill", "delegate_back", "develop_self"]


def build_critic_response_format(name: str, score_keys: tuple[str, ...]) -> dict[str, object]:
    """Build a strict JSON-schema response format for a critic role."""
    assessment_schema = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "verdict": {"type": "string", "enum": _VERDICTS},
            "scores": {
                "type": "object",
                "properties": {k: {"type": "integer"} for k in score_keys},
                "required": list(score_keys),
                "additionalProperties": False,
            },
            "objections": {"type": ["string", "null"]},
            "feedback_for_originator": {"type": ["string", "null"]},
            "developed_description": {"type": ["string", "null"]},
            "merge_with": {"type": "array", "items": {"type": "string"}},
            "merged_description": {"type": ["string", "null"]},
        },
        "required": [
            "candidate_id",
            "verdict",
            "scores",
            "objections",
            "feedback_for_originator",
            "developed_description",
            "merge_with",
            "merged_description",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "assessments": {"type": "array", "items": assessment_schema},
                    "ranking": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["assessments", "ranking"],
                "additionalProperties": False,
            },
        },
    }


class CouncilCritic:
    """Base critic: assesses a candidate pool and returns a CriticReport.

    Subclasses supply the registry role, system prompt, and score criteria.
    The critic references candidates by ID and never rewrites them — the
    synthesiser receives surviving originals alongside this report.
    """

    role: str = ""
    system_prompt: str = ""
    score_keys: tuple[str, ...] = ()

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router
        self._response_format = build_critic_response_format(
            f"{type(self).__name__}Report",
            self.score_keys,
        )

    async def run(
        self,
        candidates: Sequence[CandidateLike],
        profile: ProfessionalProfile,
        evidence: str = "",
    ) -> CriticReport:
        """Assess the pool; ``evidence`` carries dated findings and graph
        context so the critic can weigh how the landscape evolved."""
        logger.info("%s: assessing %d candidates", type(self).__name__, len(candidates))
        if not candidates:
            return CriticReport(assessments=[], ranking=[])

        user_msg = (
            f"## CANDIDATES\n\n{format_pool(candidates)}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        if evidence:
            user_msg += f"\n\n## EVIDENCE (dated)\n\n{evidence}"
        result = await self._router.call(
            role=self.role,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            response_format=self._response_format,
        )
        report = parse_critic_report(result["content"], candidates, type(self).__name__)
        logger.info(
            "%s: %d keep, %d kill, %d delegate_back, %d develop_self",
            type(self).__name__,
            *(
                sum(1 for a in report.assessments if a.verdict == v)
                for v in ("keep", "kill", "delegate_back", "develop_self")
            ),
        )
        return report


def parse_critic_report(
    content: str,
    candidates: Sequence[CandidateLike],
    agent_name: str,
) -> CriticReport:
    """Validate a raw critic report and repair omissions defensively.

    Unknown IDs are dropped, unassessed candidates default to keep, and
    the ranking is rebuilt to contain exactly the survivors — excluding
    candidates absorbed into another survivor's merge_with, which reach
    the synthesiser as merge material rather than standalone items.
    """
    parsed = json.loads(content)
    report = CriticReport.model_validate(parsed)
    known_ids = {c.candidate_id for c in candidates}

    assessments = [a for a in report.assessments if a.candidate_id in known_ids]
    assessed_ids = {a.candidate_id for a in assessments}
    for candidate in candidates:
        if candidate.candidate_id not in assessed_ids:
            logger.warning(
                "%s: no assessment for %s — defaulting to keep",
                agent_name,
                candidate.candidate_id,
            )
            assessments.append(
                CriticAssessment(candidate_id=candidate.candidate_id, verdict="keep")
            )

    survivors = {a.candidate_id for a in assessments if a.verdict in ("keep", "develop_self")}
    absorbed = {
        merge_id
        for a in assessments
        if a.verdict in ("keep", "develop_self")
        for merge_id in a.merge_with
    }
    ranking = [cid for cid in report.ranking if cid in survivors and cid not in absorbed]
    ranking += [cid for cid in sorted(survivors) if cid not in ranking and cid not in absorbed]
    return CriticReport(assessments=assessments, ranking=ranking)
