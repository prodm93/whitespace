import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    input_per_1m: float
    output_per_1m: float


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    provider: str
    timeout_seconds: int
    retries: int
    pricing: ModelPricing


class ModelRegistry:
    """Loads model_registry.yaml and provides fallback chains by role name."""

    def __init__(self, registry_path: Path) -> None:
        self._chains: dict[str, list[ModelEntry]] = {}
        self._load(registry_path)

    def _load(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text())
        for role, role_config in raw.items():
            entries: list[ModelEntry] = []
            for m in role_config["models"]:
                entries.append(
                    ModelEntry(
                        model_id=m["model_id"],
                        provider=m["provider"],
                        timeout_seconds=m["timeout_seconds"],
                        retries=m["retries"],
                        pricing=ModelPricing(
                            input_per_1m=m["pricing"]["input_per_1m"],
                            output_per_1m=m["pricing"]["output_per_1m"],
                        ),
                    )
                )
            self._chains[role] = entries
        logger.info("ModelRegistry: loaded %d roles", len(self._chains))

    def get_chain(self, role: str) -> list[ModelEntry]:
        chain = self._chains.get(role)
        if chain is None:
            raise KeyError(f"No model chain registered for role={role}")
        return chain

    @property
    def roles(self) -> list[str]:
        return list(self._chains.keys())
