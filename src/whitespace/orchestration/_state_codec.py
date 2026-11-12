"""JSON-compatible dump and load of a council state between its two halves."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

Codec = tuple[Callable[[Any], Any], Callable[[Any], Any]]


def dump_state(
    state: Mapping[str, Any],
    models: Mapping[str, type[BaseModel]],
    model_lists: Mapping[str, type[BaseModel]],
    custom: Mapping[str, Codec],
) -> dict[str, Any]:
    """Convert a state to JSON-compatible data.

    ``models`` names keys that hold one pydantic model (or ``None``),
    ``model_lists`` keys that hold a list of them, and ``custom`` keys with
    their own (dump, load) pair. Every other value is kept as it is.
    """
    data: dict[str, Any] = {}
    for key, value in state.items():
        if key in custom:
            data[key] = custom[key][0](value)
        elif key in model_lists:
            data[key] = [item.model_dump(mode="json") for item in value]
        elif key in models and value is not None:
            data[key] = value.model_dump(mode="json")
        else:
            data[key] = value
    return data


def load_state(
    data: Mapping[str, Any],
    models: Mapping[str, type[BaseModel]],
    model_lists: Mapping[str, type[BaseModel]],
    custom: Mapping[str, Codec],
) -> dict[str, Any]:
    """Rebuild a state from ``dump_state`` output with the same tables."""
    state: dict[str, Any] = {}
    for key, value in data.items():
        if key in custom:
            state[key] = custom[key][1](value)
        elif key in model_lists:
            state[key] = [model_lists[key].model_validate(item) for item in value]
        elif key in models and value is not None:
            state[key] = models[key].model_validate(value)
        else:
            state[key] = value
    return state
