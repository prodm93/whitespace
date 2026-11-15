"""The caller's uploaded documents: the ownership rule for keys, and their download."""

from __future__ import annotations

import asyncio
import os

_UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


class UploadPathError(ValueError):
    """A job named a file that is not one of the caller's uploads."""


def owned_key(path: object, user_id: str) -> bool:
    """Return whether ``path`` is an upload key of ``user_id``.

    True only for a string under ``uploads/<user_id>/`` with something after the prefix
    and no empty or ``..`` segment. Local paths are never owned.
    """
    if not isinstance(path, str):
        return False
    prefix = f"uploads/{user_id}/"
    if not path.startswith(prefix) or not path[len(prefix) :]:
        return False
    return all(segment not in ("", "..") for segment in path.split("/"))


def owned_keys(paths: object, user_id: str) -> bool:
    """Return whether ``paths`` is a list whose every item is an upload key of ``user_id``.

    An empty list is owned. Anything that is not a list is not.
    """
    if not isinstance(paths, list):
        return False
    return all(owned_key(path, user_id) for path in paths)


async def localise_paths(paths: list[str], user_id: str) -> list[str]:
    """Download the caller's upload keys to ``/tmp/whitespace/<user_id>/``.

    Every key is checked before the first download; a key that is not the caller's
    raises ``UploadPathError``. Returns the local paths in the order of ``paths``.
    """
    import hashlib

    import boto3

    for path in paths:
        if not owned_key(path, user_id):
            raise UploadPathError("Invalid upload path")
    s3 = boto3.client("s3", region_name=_AWS_REGION)
    directory = f"/tmp/whitespace/{user_id}"
    os.makedirs(directory, exist_ok=True)
    local: list[str] = []
    for path in paths:
        digest = hashlib.md5(path.encode()).hexdigest()[:10]
        local_path = f"{directory}/{digest}_{os.path.basename(path)}"
        if not os.path.exists(local_path):
            await asyncio.to_thread(s3.download_file, _UPLOADS_BUCKET, path, local_path)
        local.append(local_path)
    return local
