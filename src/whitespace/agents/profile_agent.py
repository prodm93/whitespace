"""Extracts a structured professional profile from uploaded documents."""

from __future__ import annotations

import asyncio
import json
import logging

from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.tools.document_loader import DocumentLoader

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a professional-profile extraction specialist. You will receive \
the concatenated text of one or more professional documents (CV, resume, \
publication list, project descriptions, lab notebooks). Your task is to \
extract a structured profile from the text.

Extract the following:

1. **hard_skills** — specific technical skills: programming languages, \
frameworks, lab techniques, instruments, software tools. Be concrete \
("Python", "flow cytometry") not vague ("programming", "lab skills").

2. **domain_knowledge** — subject-matter domains the person has worked \
in ("computational biology", "semiconductor fabrication", "natural \
language processing"). Capture breadth.

3. **methodologies** — research or engineering methodologies they \
practise ("agile", "CRISPR-Cas9 gene editing", "finite element \
analysis", "randomised controlled trials").

4. **past_projects** — notable projects. For each, extract:
   - name: project or engagement name
   - description: what the project accomplished
   - technologies: tools/frameworks/technologies used
   - outcomes: key results, publications, or deliverables

5. **publication_topics** — topics covered in publications or patents.

6. **years_experience** — approximate years of professional experience, \
if determinable from dates in the text. Return null if unclear.

Return valid JSON matching the schema provided. Do not invent information \
that is not in the source text. If a field has no evidence, return an \
empty list (or null for years_experience).\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ProfessionalProfile",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "hard_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "domain_knowledge": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "methodologies": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "past_projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "technologies": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "outcomes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "name",
                            "description",
                            "technologies",
                            "outcomes",
                        ],
                        "additionalProperties": False,
                    },
                },
                "publication_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "years_experience": {
                    "type": ["integer", "null"],
                },
            },
            "required": [
                "hard_skills",
                "domain_knowledge",
                "methodologies",
                "past_projects",
                "publication_topics",
                "years_experience",
            ],
            "additionalProperties": False,
        },
    },
}


class ProfileAgent:
    """Synthesises multiple professional document uploads into one profile.

    Uses a cheap model — profile extraction is NER + classification, not
    frontier reasoning.
    """

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        loader: DocumentLoader,
    ) -> None:
        self._config = config
        self._router = router
        self._loader = loader

    async def run(self, doc_paths: list[str]) -> ProfessionalProfile:
        logger.info("ProfileAgent: analysing %d documents", len(doc_paths))
        if not doc_paths:
            raise ValueError("ProfileAgent requires at least one document path")

        texts = await asyncio.gather(*(self._loader.load(path) for path in doc_paths))
        corpus = "\n\n---\n\n".join(text for text in texts if text.strip())
        if not corpus.strip():
            raise ValueError("All uploaded documents were empty")

        result = await self._router.call(
            role="profile_extractor",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": corpus},
            ],
            temperature=0.0,
            response_format=_RESPONSE_FORMAT,
        )
        parsed = json.loads(result["content"])
        return ProfessionalProfile.model_validate(parsed)
