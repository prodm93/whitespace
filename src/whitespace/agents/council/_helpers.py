"""Shared helpers for council agents."""

from __future__ import annotations

from collections.abc import Sequence

from whitespace.schemas.critique import CandidateLike, CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile


def format_profile(profile: ProfessionalProfile) -> str:
    """Render a ProfessionalProfile as a compact text block for LLM context."""
    sections: list[str] = []
    if profile.hard_skills:
        sections.append(f"Skills: {', '.join(profile.hard_skills)}")
    if profile.domain_knowledge:
        sections.append(f"Domains: {', '.join(profile.domain_knowledge)}")
    if profile.methodologies:
        sections.append(f"Methodologies: {', '.join(profile.methodologies)}")
    if profile.publication_topics:
        sections.append(f"Publications: {', '.join(profile.publication_topics)}")
    if profile.past_projects:
        projects = "; ".join(p.name for p in profile.past_projects)
        sections.append(f"Projects: {projects}")
    return "\n".join(sections) if sections else "(no profile available)"


def format_needs(needs: list[UnmetNeed]) -> str:
    """Render selected UnmetNeeds for ideator context."""
    lines: list[str] = []
    for i, n in enumerate(needs, 1):
        lines.append(
            f"{i}. **{n.title}**: {n.description}\n"
            f"   Current state: {n.current_state}\n"
            f"   Why unmet: {n.why_unmet}"
        )
    return "\n\n".join(lines)


def format_pool(candidates: Sequence[CandidateLike]) -> str:
    """Render the candidate pool for the critic, with IDs and source models."""
    sections: list[str] = []
    for c in candidates:
        sections.append(
            f"- id: {c.candidate_id} | source model: {c.source_model}\n"
            f"  **{c.title}**\n"
            f"  {c.description}"
        )
    return "\n\n".join(sections)


def format_for_synthesis(pool: Sequence[CandidateLike], report: CriticReport) -> str:
    """Render ranked survivors with full original text plus critic guidance.

    The synthesiser always sees the originals — the critic curates by ID
    and never becomes a lossy rewrite bottleneck.
    """
    by_id = {c.candidate_id: c for c in pool}
    sections: list[str] = []
    for rank, cid in enumerate(report.ranking, 1):
        candidate = by_id.get(cid)
        if candidate is None:
            continue
        assessment = report.assessment_for(cid)
        lines = [
            f"{rank}. [{cid}] **{candidate.title}** (source model: {candidate.source_model})",
            f"   {candidate.description}",
        ]
        if assessment:
            if assessment.scores:
                scored = ", ".join(f"{k}: {v}" for k, v in assessment.scores.items())
                lines.append(f"   Critic scores: {scored}")
            if assessment.objections:
                lines.append(f"   Critic notes: {assessment.objections}")
            if assessment.developed_description:
                lines.append(f"   Critic's developed version: {assessment.developed_description}")
            for merge_id in assessment.merge_with:
                merged = by_id.get(merge_id)
                if merged is not None:
                    lines.append(
                        f"   Combine with [{merge_id}] **{merged.title}** "
                        f"(source model: {merged.source_model}): {merged.description}"
                    )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
