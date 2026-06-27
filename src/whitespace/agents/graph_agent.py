"""Graph agent — populates the knowledge graph via Graphiti add_episode.

Per-document dispatch:
* ``.json`` → validate, pass with ``source=EpisodeType.json``
* ``.txt`` → read UTF-8, pass with ``source=EpisodeType.text``
* anything else → extract via ``DocumentLoader``, pass as text

Per-document failures are logged and skipped — one bad file must not
abort ingestion of the rest. The aggregate outcome is returned as an
:class:`IngestResult`.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graphiti_core.nodes import EpisodeType

from whitespace.config import Config
from whitespace.domain import IngestResult
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.schemas.ontology import OntologyDefinition
from whitespace.schemas.ontology_compiler import compile_ontology
from whitespace.tools.document_loader import DocumentLoader
from whitespace.tools.json_reader import JsonReader
from whitespace.tools.retry import retry_async
from whitespace.tools.text_reader import TextReader

logger = logging.getLogger(__name__)


class GraphAgent:
    """Drives Graphiti to ingest documents and materialise the knowledge graph."""

    def __init__(
        self,
        config: Config,
        graphiti: GraphitiClient,
        loader: DocumentLoader,
    ) -> None:
        self._config = config
        self._graphiti = graphiti
        self._loader = loader
        self._json_reader = JsonReader()
        self._text_reader = TextReader()

    async def run(
        self,
        doc_paths: list[str],
        ontology: OntologyDefinition,
    ) -> IngestResult:
        if not doc_paths:
            logger.info("GraphAgent: no documents to ingest")
            return IngestResult(documents_processed=0)

        entity_types, edge_types, edge_type_map = compile_ontology(ontology)
        group_id = self._config.graphiti_namespace
        logger.info(
            "GraphAgent: ingesting %d documents into group=%s "
            "(ontology: %d entity types, %d edge types, %d mappings)",
            len(doc_paths),
            group_id,
            len(entity_types),
            len(edge_types),
            len(edge_type_map),
        )

        successes = 0
        failures = 0
        failed: list[str] = []
        for path in doc_paths:
            try:
                await self._ingest_one(
                    path=path,
                    group_id=group_id,
                    entity_types=entity_types,
                    edge_types=edge_types,
                    edge_type_map=edge_type_map,
                )
                successes += 1
            except Exception:
                failures += 1
                failed.append(Path(path).name)
                logger.exception("GraphAgent: failed to ingest %s", path)

        logger.info(
            "GraphAgent: ingestion complete — %d ok, %d failed",
            successes,
            failures,
        )
        return IngestResult(
            documents_processed=successes,
            documents_failed=failures,
            failed_files=failed,
        )

    async def _ingest_one(
        self,
        *,
        path: str,
        group_id: str,
        entity_types: dict[str, Any],
        edge_types: dict[str, Any],
        edge_type_map: dict[tuple[str, str], list[str]],
    ) -> None:
        suffix = Path(path).suffix.lower()
        name = Path(path).name

        episode_body, source, source_description = await self._read_episode(path, suffix, name)

        await retry_async(
            self._call_add_episode,
            name,
            episode_body,
            source_description,
            source,
            group_id,
            entity_types,
            edge_types,
            edge_type_map,
            retries=2,
            base_delay=2.0,
            max_delay=15.0,
        )

    async def _read_episode(
        self, path: str, suffix: str, name: str
    ) -> tuple[str, EpisodeType, str]:
        if suffix == ".json":
            episode_body = await self._json_reader.read_text(path)
            if not episode_body.strip():
                raise ValueError(f"JSON document is empty: {name}")
            parsed = json.loads(episode_body)
            if parsed is None or parsed == {} or parsed == []:
                raise ValueError(f"JSON document has no content: {name}")
            return episode_body, EpisodeType.json, f"JSON document: {name}"

        if suffix == ".txt":
            episode_body = await self._text_reader.read(path)
            if not episode_body.strip():
                raise ValueError(f"Text document is empty: {name}")
            return episode_body, EpisodeType.text, f"Text document: {name}"

        episode_body = await self._loader.load(path)
        if not episode_body.strip():
            raise ValueError(f"Document yielded no extractable text: {name}")
        return episode_body, EpisodeType.text, f"Document: {name}"

    async def _call_add_episode(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        source: EpisodeType,
        group_id: str,
        entity_types: dict[str, Any],
        edge_types: dict[str, Any],
        edge_type_map: dict[tuple[str, str], list[str]],
    ) -> None:
        await self._graphiti.graphiti.add_episode(
            name=name,
            episode_body=episode_body,
            source_description=source_description,
            reference_time=datetime.now(UTC),
            source=source,
            group_id=group_id,
            entity_types=entity_types or None,
            edge_types=edge_types or None,
            edge_type_map=edge_type_map or None,
        )
