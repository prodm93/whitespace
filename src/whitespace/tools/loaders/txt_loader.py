"""TXT loader (stdlib UTF-8 read)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TxtLoader:
    """Reads a plain-text file as UTF-8."""

    def load(self, path: str) -> str:
        p = Path(path)
        if not p.is_file():
            raise ValueError(f"Text file not found: {path}")
        return p.read_text(encoding="utf-8", errors="replace")
