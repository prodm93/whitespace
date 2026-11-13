"""The pipeline image must copy every module of the pipeline function's folder."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FUNCTION_DIR = _ROOT / "deploy" / "aws" / "lambda" / "pipeline_orchestrator"
_DOCKERFILE = _ROOT / "deploy" / "aws" / "Dockerfile"
_PREFIX = "deploy/aws/lambda/pipeline_orchestrator/"


def _copied_function_files(dockerfile: str) -> set[str]:
    """Names of the files that the ``COPY`` instruction of the function folder copies."""
    joined = dockerfile.replace("\\\n", " ")
    for line in joined.splitlines():
        if line.startswith("COPY") and _PREFIX in line:
            return {Path(source).name for source in re.findall(rf"{_PREFIX}\S+", line)}
    return set()


def test_every_function_module_is_copied_into_the_image() -> None:
    modules = {path.name for path in _FUNCTION_DIR.glob("*.py")}

    missing = modules - _copied_function_files(_DOCKERFILE.read_text())

    assert missing == set(), f"add to the COPY list of deploy/aws/Dockerfile: {sorted(missing)}"
