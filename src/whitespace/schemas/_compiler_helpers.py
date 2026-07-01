"""Helpers for :mod:`ontology_compiler` — field-to-Pydantic conversion."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, create_model

from whitespace.schemas.ontology import SchemaFieldDefinition
from whitespace.schemas.ontology_name_sanitiser import (
    sanitise_field_name,
)
from whitespace.schemas.ontology_type_resolution import resolve_type

logger = logging.getLogger(__name__)


def fields_to_pydantic(
    fields: list[SchemaFieldDefinition],
    *,
    owner: str,
    protected: frozenset[str] = frozenset(),
) -> dict[str, tuple[Any, Any]]:
    """Convert schema field definitions into ``create_model`` kwargs."""
    pydantic_fields: dict[str, tuple[Any, Any]] = {}
    seen: set[str] = set()
    for field_def in fields:
        sanitised = sanitise_field_name(field_def.name)
        if sanitised is None:
            logger.warning(
                "ontology_compiler: dropping field on %s — empty/invalid name %r",
                owner,
                field_def.name,
            )
            continue
        while sanitised in protected:
            sanitised = f"{sanitised}_"
        if sanitised in seen:
            logger.warning(
                "ontology_compiler: dropping duplicate field %r on %s (after sanitising %r)",
                sanitised,
                owner,
                field_def.name,
            )
            continue
        seen.add(sanitised)

        if sanitised != field_def.name:
            logger.warning(
                "ontology_compiler: renamed field on %s: %r -> %r",
                owner,
                field_def.name,
                sanitised,
            )

        py_type = resolve_type(field_def.type_name)
        description = field_def.description
        if sanitised != field_def.name:
            description = f"{description} (original name: {field_def.name})"

        if field_def.required and "None" not in field_def.type_name:
            default: Any = Field(..., description=description)
        else:
            default = Field(default=None, description=description)
            if py_type is not type(None) and "None" not in str(py_type):
                py_type = py_type | None

        pydantic_fields[sanitised] = (py_type, default)
    return pydantic_fields


def compile_model(
    *,
    sanitised_name: str,
    original_name: str,
    description: str,
    fields: list[SchemaFieldDefinition],
    protected: frozenset[str] = frozenset(),
) -> type[BaseModel]:
    """Compile a single ontology type definition into a runtime BaseModel."""
    pydantic_fields = fields_to_pydantic(fields, owner=sanitised_name, protected=protected)
    model = create_model(sanitised_name, **pydantic_fields)  # type: ignore[call-overload]
    if sanitised_name != original_name:
        model.__doc__ = f"{description} (original name: {original_name})"
    else:
        model.__doc__ = description
    return model
