"""Ontology agent — infers entity/edge type definitions from patent corpus.

Fully dynamic: the agent examines a sample of the corpus and produces
an :class:`OntologyDefinition` describing what kinds of things exist and
how they connect. The system prompt gives patent-domain examples but the
agent is free to infer whatever types the corpus warrants.

An empty :class:`OntologyDefinition` from :meth:`run` means "use Graphiti's
default extraction with no custom ontology", not "the ontology is empty".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.ontology import OntologyDefinition
from whitespace.tools.document_loader import DocumentLoader
from whitespace.tools.json_reader import JsonReader
from whitespace.tools.text_reader import TextReader

logger = logging.getLogger(__name__)

_MAX_DOCS_SAMPLED = 5
_MAX_CHARS_PER_DOC = 2000
_MAX_JSON_SAMPLE_BYTES = 4000

_SYSTEM_PROMPT = """\
You are an ontology engineer specialising in patent analysis. From the \
provided document samples you must infer a knowledge-graph ontology: \
entity TYPES, edge TYPES, and the allowed \
(source_entity_type, target_entity_type) → [edge_type_names] mappings.

Do NOT extract specific instances — only type definitions and mappings.

The documents are patent filings, technical papers, and web sources \
about a patent landscape. Common entity types in patent domains include \
(but are not limited to):
- Patent, Claim, Limitation, Inventor, Assignee
- TechnicalDomain, Method, Material, Component, Standard

Common edge types include (but are not limited to):
- cites, improves_upon, limited_by, applies_method
- addresses_limitation, invented_by, assigned_to
- composed_of, related_to, competes_with

These are EXAMPLES. Infer the actual types from the corpus. Different \
domains produce very different ontologies — battery patents will have \
types like Electrolyte or CellArchitecture; software patents will have \
types like Protocol or Algorithm.

Rules:
- Each entity/edge type must include a concise description.
- Use Python-style type names for fields: 'str', 'int', 'float', \
'bool', or 'str | None'.
- Entity type names should be PascalCase.
- Edge type names should be SCREAMING_SNAKE_CASE.
- Keep the ontology focused — prefer 8-15 entity types and 10-20 \
edge types over exhaustive taxonomies.\
"""


class OntologyAgent:
    """Infers a serialisable ontology from a sample of the patent corpus."""

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        loader: DocumentLoader,
    ) -> None:
        self._config = config
        self._router = router
        self._loader = loader
        self._json_reader = JsonReader()
        self._text_reader = TextReader()

    async def run(
        self,
        doc_paths: list[str],
        extra_samples: list[tuple[str, str]] | None = None,
    ) -> OntologyDefinition:
        """Infer the ontology from file samples plus optional (name, text) pairs.

        ``extra_samples`` lets research findings shape the ontology alongside
        uploaded files, so the inferred types reflect the whole corpus.
        """
        extra_samples = extra_samples or []
        logger.info(
            "OntologyAgent: analysing %d documents, %d extra samples",
            len(doc_paths),
            len(extra_samples),
        )
        if not doc_paths and not extra_samples:
            return self._empty_fallback(reason="no documents supplied")

        samples = await self._collect_samples(doc_paths[:_MAX_DOCS_SAMPLED])
        samples.extend(extra_samples[: max(0, _MAX_DOCS_SAMPLED - len(samples))])
        if not samples:
            return self._empty_fallback(
                reason=f"no readable samples in {len(doc_paths)} document(s)"
            )

        try:
            ontology = await self._infer(samples)
        except Exception:
            logger.exception("OntologyAgent: ontology inference failed")
            return self._empty_fallback(reason="LLM inference error")

        logger.info(
            "OntologyAgent: inferred %d entity types, %d edge types, %d mappings",
            len(ontology.entity_types),
            len(ontology.edge_types),
            len(ontology.edge_type_map),
        )
        return ontology

    async def _infer(self, samples: list[tuple[str, str]]) -> OntologyDefinition:
        schema = json.dumps(OntologyDefinition.model_json_schema(), indent=2)
        sample_blocks = "\n\n".join(f"### {name}\n{content}" for name, content in samples)
        user_msg = (
            f"Return ONLY a JSON object that validates against this schema:\n"
            f"```json\n{schema}\n```\n\n"
            f"Document samples:\n{sample_blocks}"
        )
        result = await self._router.call(
            role="ontology_inference",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = result["content"]
        try:
            return OntologyDefinition.model_validate_json(content)
        except ValidationError:
            logger.warning("OntologyAgent: response failed validation, retrying parse")
            parsed = json.loads(content)
            return OntologyDefinition.model_validate(parsed)

    async def _collect_samples(self, doc_paths: list[str]) -> list[tuple[str, str]]:
        samples: list[tuple[str, str]] = []
        for path in doc_paths:
            try:
                sample = await self._sample_one(path)
            except Exception:
                logger.warning("OntologyAgent: skipping unreadable %s", path, exc_info=True)
                continue
            if sample:
                samples.append((Path(path).name, sample))
        return samples

    async def _sample_one(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".json":
            text = await self._json_reader.read_text(path)
            return text[:_MAX_JSON_SAMPLE_BYTES]
        if suffix == ".txt":
            text = await self._text_reader.read(path)
            return text[:_MAX_CHARS_PER_DOC]
        text = await self._loader.load(path)
        return text[:_MAX_CHARS_PER_DOC]

    def _empty_fallback(self, *, reason: str) -> OntologyDefinition:
        logger.warning(
            "OntologyAgent: returning empty ontology — ingestion will proceed "
            "without custom ontology (Graphiti default extraction). Reason: %s",
            reason,
        )
        return OntologyDefinition()
