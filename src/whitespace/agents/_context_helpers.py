"""Rendering helpers for ContextAgent."""

from __future__ import annotations

from whitespace.domain import Edge

_MAX_CHUNK_CHARS = 800

EMPTY_CONTEXT = "No relevant information found in the knowledge graph."


def collect_episode_uuids(edges: list[Edge], *, max_chunks: int) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        for ep_uuid in edge.properties.get("episodes", []) or []:
            if ep_uuid not in seen:
                seen.add(ep_uuid)
                order.append(ep_uuid)
                if len(order) >= max_chunks:
                    return order
    return order


def render(
    edges: list[Edge],
    name_by_uuid: dict[str, str],
    episode_order: list[str],
    chunks: dict[str, dict[str, str]],
) -> str:
    def label(uuid: str) -> str:
        return name_by_uuid.get(uuid) or uuid[:8]

    facts_block: list[str] = ["## Most relevant facts"]
    for edge in edges:
        src = label(edge.source_id)
        tgt = label(edge.target_id)
        props = edge.properties or {}
        fact = props.get("fact", "")
        line = f"- **{edge.edge_type}** ({src} → {tgt})"
        if fact:
            line += f": {fact}"
        time_bits: list[str] = []
        valid_at = props.get("valid_at")
        invalid_at = props.get("invalid_at")
        ref = props.get("reference_time")
        if valid_at:
            time_bits.append(f"valid from {valid_at}")
        if invalid_at:
            time_bits.append(f"invalid from {invalid_at}")
        if ref and not valid_at:
            time_bits.append(f"observed at {ref}")
        if time_bits:
            line += f"  _[{'; '.join(time_bits)}]_"
        facts_block.append(line)
    sections: list[str] = ["\n".join(facts_block)]

    if episode_order and chunks:
        excerpt_block: list[str] = ["## Source excerpts"]
        for ep_uuid in episode_order:
            chunk = chunks.get(ep_uuid)
            if not chunk:
                continue
            content = chunk.get("content", "").strip()
            if not content:
                continue
            if len(content) > _MAX_CHUNK_CHARS:
                content = content[:_MAX_CHUNK_CHARS].rstrip() + "…"
            name = chunk.get("name", "") or ep_uuid[:8]
            excerpt_block.append(f"### {name}\n{content}")
        if len(excerpt_block) > 1:
            sections.append("\n\n".join(excerpt_block))

    has_facts = len(facts_block) > 1
    return "\n\n".join(sections) if has_facts else EMPTY_CONTEXT
