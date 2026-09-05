"""Prompts and response formats for the gap identifier."""

from __future__ import annotations

from whitespace.agents.council._question_proposals import QUESTION_PROPOSALS_SCHEMA

QUERY_PROMPT = """\
You are a patent-landscape analyst preparing to research a domain for a \
specific professional. Write {n} clever, diverse search queries to map \
the landscape: the domain's core technologies, its known limitations \
and complaints ("fails to", "cannot", "limited by"), adjacent fields \
whose methods might transfer, and the areas closest to this user's \
skills. Vary vocabulary; patents, papers and web commentary name the \
same problems differently. Return JSON: {{"queries": ["...", ...]}}.\
"""

EXPLORE_PROMPT = """\
You are a patent-landscape analyst hunting for unmet needs that match a \
specific professional's expertise.

You have tools to explore a KNOWLEDGE GRAPH built from this user's own \
background documents together with the domain research (patents, papers, \
web sources). Its defining value: it connects THIS USER's experience to \
the research landscape. The paths between what this person has done \
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

1. RAW RESEARCH FINDINGS: verbatim, dated search results from USPTO, \
Semantic Scholar and the web, exactly as retrieved.

2. GRAPH EXPLORATION: what you surfaced by traversing the knowledge \
graph, whose value is relational: it connects this user's own \
experience and background to the research landscape, and shows how \
technologies, limitations and prior work interlink.

Identify **unmet needs** in the patent landscape specifically relevant \
to this user's expertise. An unmet need is a gap where:
- Existing patents or solutions are inadequate, limited, or missing
- The user's specific skills position them to contribute a novel solution
- There is evidence in either channel. The strongest gaps are \
corroborated by both

For each gap:
- **title**: concise name (5-10 words)
- **description**: 3-5 sentences covering what the gap is, why it \
matters, and which evidence (cite the channel) supports it
- **evidence**: the exact evidence behind this gap: finding keys from the RAW RESEARCH \
FINDINGS channel (e.g. "[F7]") and short references for graph-channel support (e.g. \
"graph: path from the user's electrochemistry work to the ceramic cracking limitation"). \
Cite at least one item per gap; claims without citations will be treated as unsupported.

## QUESTIONS FOR THE USER

Propose questions whenever the user's answer could materially sharpen the analysis or \
unlock a stronger candidate. Omit questions that are banal, generic, already answered by \
the supplied material, or unlikely to change a candidate, its supporting evidence, or the \
next research step. A separate gate decides whether to interrupt the user, so do not \
suppress a genuinely high-value proposal yourself.

Return up to 5 proposals in `questions_for_user`. For each proposal:

- Ask one focused question that the user can answer from their own knowledge, experience, \
constraints, resources, preferences, or observations. Do not ask the user to perform research.
- Use `clarify` when the answer could resolve an ambiguity that affects how you interpret \
the evidence, compare gaps, or direct follow-up research.
- Use `unlock` when the answer could make a promising candidate gap supportable, reveal a \
stronger formulation of it, or open a concrete path that the available evidence cannot \
establish alone.
- In `rationale`, identify the finding or graph connection that raised the question and \
state exactly what the answer could change.
- In `hypothesis`, state your current best answer in concise, falsifiable form so the user \
can confirm or correct it. A low-confidence hypothesis is acceptable; `unknown` is not.
- For `unlock`, set `related_candidate_title` to the exact title of the candidate gap it \
could unlock. For `clarify`, set it to an empty string.

Questions supplement the candidate gaps. Do not withhold or weaken a candidate because an \
answer is unavailable.

You may also receive PRIOR ANALYSES AND REJECTIONS: gaps this system \
already surfaced in earlier runs, and gaps previously rejected with the \
reason. Do NOT resurface either kind. Build beyond them: sharper, \
adjacent, or newly-opened gaps only.

Aim for 5-8 candidate gaps; never fewer than 4. Prefer specificity \
over breadth. Ground every gap in something concrete.\
"""

REVISION_PROMPT = """\
You are a patent-landscape analyst revising your own earlier candidate \
gaps. A council critic reviewed them and returned specific feedback on \
each.

For each candidate below, produce a revised version that addresses the \
critic's feedback: sharpen specificity, strengthen the evidence, and \
deepen the connection to the user's profile. Keep what was already \
strong. Do not change the subject of a candidate; develop it.

Return exactly one revised gap per candidate, in the same order, with \
the same output shape: title, description and evidence. Keep citations that still hold; \
add keys for any new support you invoke.\
"""

NEIGHBOUR_CRAFT_BLOCK = """\


## RELATED PRIOR CONTEXT (other domains; judge relevance before reusing)

{neighbours}

These findings come from previous runs on different domains. For each one, decide whether \
the underlying problem matches a research angle you are considering. If a finding already \
answers that angle, do not spend a query on it; you will be able to cite it as evidence \
instead. If it is close but insufficient (different material, different constraint, different \
context), research fresh and note the difference.\
"""

NEIGHBOUR_CONCLUDE_BLOCK = """\


## RELATED PRIOR CONTEXT (semantic neighbours from other domains)

{neighbours}

These are labelled with their source domain, similarity to the current domain, and date. \
Judge relevance yourself. If you rely on a neighbour in a gap, justify its inclusion in that \
gap's description.\
"""

_GAPS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "description", "evidence"],
        "additionalProperties": False,
    },
}

GAPS_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "CandidateGaps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "gaps": _GAPS_SCHEMA,
                "questions_for_user": QUESTION_PROPOSALS_SCHEMA,
            },
            "required": ["gaps", "questions_for_user"],
            "additionalProperties": False,
        },
    },
}

GAP_REVISIONS_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "RevisedCandidateGaps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"gaps": _GAPS_SCHEMA},
            "required": ["gaps"],
            "additionalProperties": False,
        },
    },
}
