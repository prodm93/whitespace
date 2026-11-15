"""Every region setting of the app and its deployment is ``us-east-1``.

The Terraform state backend is the one exception: its bucket can live in another region.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_STATE_BACKEND = _ROOT / "deploy" / "aws" / "terraform" / "backend.tf"
_SKIPPED_DIRS = {".terraform", "__pycache__"}


def _files_naming(text: bytes) -> list[str]:
    found = []
    for top in ("deploy", "src"):
        for path in (_ROOT / top).rglob("*"):
            if not path.is_file() or _SKIPPED_DIRS & set(path.parts):
                continue
            if text in path.read_bytes():
                found.append(path.relative_to(_ROOT).as_posix())
    return sorted(found)


def test_only_the_state_backend_names_sa_east_1() -> None:
    assert _files_naming(b"sa-east-1") == [_STATE_BACKEND.relative_to(_ROOT).as_posix()]
