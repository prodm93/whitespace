from abc import ABC, abstractmethod


class MetricsEmitter(ABC):
    """Abstract interface for emitting application metrics."""

    @abstractmethod
    async def emit(
        self,
        metric_name: str,
        value: float,
        dimensions: dict[str, str],
    ) -> None: ...
