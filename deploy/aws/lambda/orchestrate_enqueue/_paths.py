"""The ownership rule for upload keys, as the pipeline function applies it.

This function's package holds only its own folder, so the rule is kept here as a
second copy.
"""

from __future__ import annotations


def _owned_key(path: object, user_id: str) -> bool:
    if not isinstance(path, str):
        return False
    prefix = f"uploads/{user_id}/"
    if not path.startswith(prefix) or not path[len(prefix) :]:
        return False
    return all(segment not in ("", "..") for segment in path.split("/"))


def owned_keys(paths: object, user_id: str) -> bool:
    """Return whether ``paths`` is a list whose every item is an upload key of ``user_id``.

    A key is owned when it is a string under ``uploads/<user_id>/`` with something after
    the prefix and no empty or ``..`` segment. An empty list is owned.
    """
    if not isinstance(paths, list):
        return False
    return all(_owned_key(path, user_id) for path in paths)
