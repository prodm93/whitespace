"""Compile a serialisable :class:`OntologyDefinition` into Graphiti's runtime dicts.

Graphiti's ``add_episode`` accepts ``entity_types``, ``edge_types``, and
``edge_type_map``. This module converts the JSON-safe ontology description
into those runtime dicts, delegating field compilation and name sanitisation
to :mod:`_compiler_helpers`, :mod:`ontology_name_sanitiser`, and
:mod:`ontology_type_resolution`.
"""

from __future__ import annotations

import logging

from graphiti_core.nodes import EntityNode
from pydantic import BaseModel
from whitespace.schemas._compiler_helpers import compile_model

from whitespace.schemas.ontology import OntologyDefinition
from whitespace.schemas.ontology_name_sanitiser import sanitise_class_name

logger = logging.getLogger(__name__)

_PROTECTED_ENTITY_FIELD_NAMES: frozenset[str] = frozenset(EntityNode.model_fields.keys())


def compile_ontology(
    ontology: OntologyDefinition,
) -> tuple[
    dict[str, type[BaseModel]],
    dict[str, type[BaseModel]],
    dict[tuple[str, str], list[str]],
]:
    """Return ``(entity_types, edge_types, edge_type_map)`` ready for Graphiti."""
    entity_name_map: dict[str, str] = {}
    entity_types: dict[str, type[BaseModel]] = {}
    for entity in ontology.entity_types:
        sanitised = sanitise_class_name(entity.name)
        if sanitised is None:
            logger.warning(
                "ontology_compiler: dropping entity type with invalid name %r",
                entity.name,
            )
            continue
        if sanitised in entity_types:
            logger.warning(
                "ontology_compiler: dropping duplicate entity type %r (after sanitising %r)",
                sanitised,
                entity.name,
            )
            continue
        if sanitised != entity.name:
            logger.warning(
                "ontology_compiler: renamed entity type %r -> %r",
                entity.name,
                sanitised,
            )
        try:
            entity_types[sanitised] = compile_model(
                sanitised_name=sanitised,
                original_name=entity.name,
                description=entity.description,
                fields=entity.fields,
                protected=_PROTECTED_ENTITY_FIELD_NAMES,
            )
        except Exception:
            logger.exception("ontology_compiler: failed to compile entity type %s", sanitised)
            continue
        entity_name_map[entity.name] = sanitised

    edge_name_map: dict[str, str] = {}
    edge_types: dict[str, type[BaseModel]] = {}
    for edge in ontology.edge_types:
        sanitised = sanitise_class_name(edge.name)
        if sanitised is None:
            logger.warning(
                "ontology_compiler: dropping edge type with invalid name %r",
                edge.name,
            )
            continue
        if sanitised in edge_types:
            logger.warning(
                "ontology_compiler: dropping duplicate edge type %r (after sanitising %r)",
                sanitised,
                edge.name,
            )
            continue
        if sanitised != edge.name:
            logger.warning(
                "ontology_compiler: renamed edge type %r -> %r",
                edge.name,
                sanitised,
            )
        try:
            edge_types[sanitised] = compile_model(
                sanitised_name=sanitised,
                original_name=edge.name,
                description=edge.description,
                fields=edge.fields,
            )
        except Exception:
            logger.exception("ontology_compiler: failed to compile edge type %s", sanitised)
            continue
        edge_name_map[edge.name] = sanitised

    edge_type_map: dict[tuple[str, str], list[str]] = {}
    for mapping in ontology.edge_type_map:
        src = entity_name_map.get(mapping.source_entity_type)
        tgt = entity_name_map.get(mapping.target_entity_type)
        if src is None or tgt is None:
            logger.warning(
                "ontology_compiler: dropping edge_type_map entry "
                "(%r -> %r) — missing entity type after sanitisation",
                mapping.source_entity_type,
                mapping.target_entity_type,
            )
            continue
        resolved_edges: list[str] = []
        for edge_name in mapping.edge_type_names:
            sanitised_edge = edge_name_map.get(edge_name)
            if sanitised_edge is None:
                logger.warning(
                    "ontology_compiler: dropping edge name %r from mapping "
                    "(%r -> %r) — missing after sanitisation",
                    edge_name,
                    mapping.source_entity_type,
                    mapping.target_entity_type,
                )
                continue
            resolved_edges.append(sanitised_edge)
        if resolved_edges:
            edge_type_map[(src, tgt)] = resolved_edges

    # Catch-all: ("Entity", "Entity") applies all edge types to any pair.
    # Without it, unclassified pairs degrade to RELATES_TO.
    if edge_types:
        edge_type_map[("Entity", "Entity")] = list(edge_types.keys())

    return entity_types, edge_types, edge_type_map
