"""Shared helpers for council agents."""

from __future__ import annotations

from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.idea import CandidateIdea
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


def format_candidates(all_gaps: list[list[CandidateGap]]) -> str:
    """Render grouped candidate gaps for the critic's user message."""
    sections: list[str] = []
    for i, gaps in enumerate(all_gaps, 1):
        model = gaps[0].source_model if gaps else "unknown"
        lines = [f"### Analyst {i} (model: {model})"]
        for g in gaps:
            lines.append(f"- **{g.title}**: {g.description}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


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


def format_idea_candidates(all_ideas: list[list[CandidateIdea]]) -> str:
    """Render grouped candidate ideas for the critic's user message."""
    sections: list[str] = []
    for i, ideas in enumerate(all_ideas, 1):
        framing = ideas[0].framing if ideas else "unknown"
        model = ideas[0].source_model if ideas else "unknown"
        lines = [f"### Analyst {i} (model: {model}, framing: {framing})"]
        for idea in ideas:
            lines.append(f"- **{idea.title}**: {idea.description}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
