import logging

from whitespace.observability.metrics import MetricsEmitter

logger = logging.getLogger(__name__)


class LocalMetricsEmitter(MetricsEmitter):
    """Logs metrics as structured key=value pairs to console. For BYOK Docker mode."""

    async def emit(
        self,
        metric_name: str,
        value: float,
        dimensions: dict[str, str],
    ) -> None:
        dims = " ".join(f"{k}={v}" for k, v in dimensions.items())
        logger.info("metric=%s value=%.4f %s", metric_name, value, dims)
