"""Episode-chunk queries over Neo4j.

Source ``Episodic`` nodes hold the original text Graphiti ingested via
``add_episode``. Pulling them back per surfaced edge lets the generator
ground specific phrasing in the corpus.
"""

from __future__ import annotations

import logging

from whitespace.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


_FETCH_EPISODE_CHUNKS_CYPHER = """
MATCH (e:Episodic)
WHERE e.uuid IN $uuids AND e.group_id = $group_id
RETURN e.uuid AS uuid, e.name AS name, e.content AS content,
       toString(e.created_at) AS created_at,
       e.source_description AS source_description
"""


class GraphEpisodeTools:
    """Episode-side reads. Only needs the Neo4j driver."""

    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    async def fetch_episode_chunks(
        self,
        episode_uuids: list[str],
        group_id: str,
    ) -> dict[str, dict[str, str]]:
        """Fetch source episode contents by UUID, scoped to ``group_id``."""
        if not episode_uuids:
            return {}
        try:
            async with self._neo4j.driver.session(database=self._neo4j.database) as session:
                records = await session.run(
                    _FETCH_EPISODE_CHUNKS_CYPHER,
                    uuids=list(set(episode_uuids)),
                    group_id=group_id,
                )
                rows = [record.data() async for record in records]
        except Exception:
            logger.exception(
                "fetch_episode_chunks failed for %d uuids in group=%s",
                len(episode_uuids),
                group_id,
            )
            return {}
        out: dict[str, dict[str, str]] = {}
        for row in rows:
            uuid = row.get("uuid")
            if not uuid:
                continue
            out[uuid] = {
                "name": row.get("name") or "",
                "content": row.get("content") or "",
                "created_at": row.get("created_at") or "",
                "source_description": row.get("source_description") or "",
            }
        return out
