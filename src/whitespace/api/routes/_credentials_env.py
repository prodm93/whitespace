"""Reading and writing the credentials ``.env`` file (mode 600)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

ENV_FILE = Path(os.environ.get("CREDS_ENV_FILE", ".env"))


def parse_dotenv_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "" or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip().upper()
        value = line[eq + 1 :].strip()
        if key == "":
            continue
        out[key] = value
    return out


def persist_env(pairs: dict[str, str]) -> None:
    """Merge the pairs into the file in one step; a failed write leaves the old file whole.

    The new content goes to a temporary file (mode 600) in the same directory,
    which then replaces the target.
    """
    target = ENV_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_dotenv_lines(target.read_text()) if target.exists() else {}
    existing.update(pairs)
    content = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
