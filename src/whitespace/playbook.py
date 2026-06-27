"""Loader for the retrieval-strategy playbook.

The playbook text lives as a packaged asset
(``whitespace/assets/retrieval_playbook.md``) and is loaded once at
import time.
"""

from __future__ import annotations

from importlib.resources import files

PLAYBOOK: str = (
    files("whitespace.assets").joinpath("retrieval_playbook.md").read_text(encoding="utf-8")
)
