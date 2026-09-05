"""Concurrency tests for context enrichment reads."""

from __future__ import annotations

import asyncio
from typing import cast

from whitespace.agents.context_agent import ContextAgent
from whitespace.config import Config
from whitespace.domain import Edge
from whitespace.tools.graph_tools import GraphTools


class _NodeTools:
    def __init__(self, names_started: asyncio.Event, episodes_started: asyncio.Event) -> None:
        self._names_started = names_started
        self._episodes_started = episodes_started

    async def fetch_node_names(self, uuids: list[str], group_id: str) -> dict[str, str]:
        self._names_started.set()
        await self._episodes_started.wait()
        return {uuids[0]: "Source", uuids[1]: "Target"}


class _EpisodeTools:
    def __init__(self, names_started: asyncio.Event, episodes_started: asyncio.Event) -> None:
        self._names_started = names_started
        self._episodes_started = episodes_started

    async def fetch_episode_chunks(
        self, episode_uuids: list[str], group_id: str
    ) -> dict[str, dict[str, str]]:
        self._episodes_started.set()
        await self._names_started.wait()
        return {
            episode_uuids[0]: {
                "name": "Source episode",
                "content": "Source text",
                "created_at": "",
                "source_description": "",
            }
        }


class _GraphTools:
    def __init__(self) -> None:
        names_started = asyncio.Event()
        episodes_started = asyncio.Event()
        self.nodes = _NodeTools(names_started, episodes_started)
        self.episodes = _EpisodeTools(names_started, episodes_started)


async def test_render_edges_fetches_names_and_episodes_concurrently() -> None:
    graph_tools = cast(GraphTools, _GraphTools())
    agent = ContextAgent(Config(), graph_tools)
    edge = Edge(
        id="edge-1",
        edge_type="SUPPORTS",
        source_id="source-id",
        target_id="target-id",
        properties={"fact": "Relevant fact", "episodes": ["episode-1"]},
    )

    rendered = await asyncio.wait_for(
        agent._render_edges([edge], "test-group"),
        timeout=1,
    )

    assert "Source" in rendered
    assert "Target" in rendered
    assert "Source text" in rendered
