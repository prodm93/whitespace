"""Dispatcher that routes documents to the appropriate format-specific loader.

JSON is omitted — ``GraphAgent`` reads ``.json`` files directly and feeds them
to ``add_episode(..., source=EpisodeType.json)``, preserving structure for
Graphiti's native entity/relationship extraction.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from whitespace.tools.loaders.csv_loader import CsvLoader
from whitespace.tools.loaders.docx_loader import DocxLoader
from whitespace.tools.loaders.pdf_loader import PdfLoader
from whitespace.tools.loaders.txt_loader import TxtLoader
from whitespace.tools.loaders.xlsx_loader import XlsxLoader

logger = logging.getLogger(__name__)

_LOADERS: dict[str, type] = {
    ".pdf": PdfLoader,
    ".csv": CsvLoader,
    ".docx": DocxLoader,
    ".xlsx": XlsxLoader,
    ".txt": TxtLoader,
}


class DocumentLoader:
    """Dispatches document loading to the appropriate format-specific loader."""

    async def load(self, path: str) -> str:
        """Load a document and return its text content.

        Underlying parsers are sync and CPU-bound; ``asyncio.to_thread``
        keeps the event loop free.
        """
        return await asyncio.to_thread(self._load_sync, path)

    def _load_sync(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        loader_cls = _LOADERS.get(suffix)
        if loader_cls is None:
            raise ValueError(f"Unsupported document format: {suffix}")
        logger.info("Loading %s with %s", path, loader_cls.__name__)
        result: str = loader_cls().load(path)
        return result
