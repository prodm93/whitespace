"""Prompts and response formats for the gap identifier."""

from __future__ import annotations

QUERY_PROMPT = """\
You are a patent-landscape analyst preparing to research a domain for a \
specific professional. Write {n} clever, diverse search queries to map \
the landscape: the domain's core technologies, its known limitations \
and complaints ("fails to", "cannot", "limited by"), adjacent fields \
whose methods might transfer, and the areas closest to this user's \
skills. Vary vocabulary — patents, papers and web commentary name the \
same problems differently. Return JSON: {{"queries": ["...", ...]}}.\
"""

EXPLORE_PROMPT = """\
You are a patent-landscape analyst hunting for unmet needs that match a \
specific professional's expertise.

You have tools to explore a KNOWLEDGE GRAPH built from this user's own \
background documents together with the domain research (patents, papers, \
web sources). Its defining value: it connects THIS USER's experience to \
the research landscape — the paths between what this person has done \
and where the domain has holes are the primary signal. Citation chains, \
shared limitations and technology links are the secondary relational \
fabric. Treat it as a map of the user's position in the field, not a \
pile of documents.

Explore before concluding: start from the user's skills and follow the \
connections outward; probe limitation and complaint phrasing; inspect \
entities that sit between the user's expertise and unsolved problems. \
When your evidence is sufficient to name concrete gaps, stop calling \
tools and summarise what you found.\
"""

CONCLUDE_PROMPT = """\
You are a patent-landscape analyst. You have TWO evidence channels, \
explicitly labelled below:

1. RAW RESEARCH FINDINGS — verbatim, dated search results from USPTO, \
Semantic Scholar and the web, exactly as retrieved.

2. GRAPH EXPLORATION — what you surfaced by traversing the knowledge \
graph, whose value is relational: it connects this user's own \
experience and background to the research landscape, and shows how \
technologies, limitations and prior work interlink.

Identify **unmet needs** in the patent landscape specifically relevant \
to this user's expertise. An unmet need is a gap where:
- Existing patents or solutions are inadequate, limited, or missing
- The user's specific skills position them to contribute a novel solution
- There is evidence in either channel — and the strongest gaps are \
corroborated by both

For each gap:
- **title**: concise name (5-10 words)
- **description**: 3-5 sentences covering what the gap is, why it \
matters, and which evidence (cite the channel) supports it

You may also receive PRIOR ANALYSES AND REJECTIONS: gaps this system \
already surfaced in earlier runs, and gaps previously rejected with the \
reason. Do NOT resurface either kind. Build beyond them: sharper, \
adjacent, or newly-opened gaps only.

Aim for 5-8 candidate gaps — never fewer than 4. Prefer specificity \
over breadth. Ground every gap in something concrete.\
"""

REVISION_PROMPT = """\
You are a patent-landscape analyst revising your own earlier candidate \
gaps. A council critic reviewed them and returned specific feedback on \
each.

For each candidate below, produce a revised version that addresses the \
critic's feedback: sharpen specificity, strengthen the evidence, and \
deepen the connection to the user's profile. Keep what was already \
strong. Do not change the subject of a candidate — develop it.

Return exactly one revised gap per candidate, in the same order, with \
the same output shape: title and description.\
"""

GAPS_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "CandidateGaps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["title", "description"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["gaps"],
            "additionalProperties": False,
        },
    },
}
