import asyncio
import logging

from whitespace.observability.metrics import MetricsEmitter

logger = logging.getLogger(__name__)


class CloudWatchMetricsEmitter(MetricsEmitter):
    """Emits CloudWatch custom metrics. SaaS mode only. Lazy boto3 import."""

    def __init__(
        self,
        namespace: str = "whitespace",
        region: str = "sa-east-1",
    ) -> None:
        import boto3

        self._client = boto3.client("cloudwatch", region_name=region)
        self._namespace = namespace

    async def emit(
        self,
        metric_name: str,
        value: float,
        dimensions: dict[str, str],
    ) -> None:
        cw_dimensions = [{"Name": k, "Value": v} for k, v in dimensions.items()]
        try:
            await asyncio.to_thread(
                self._client.put_metric_data,
                Namespace=self._namespace,
                MetricData=[
                    {
                        "MetricName": metric_name,
                        "Value": value,
                        "Unit": _infer_unit(metric_name),
                        "Dimensions": cw_dimensions,
                    },
                ],
            )
        except Exception as exc:
            logger.error(
                "CloudWatch emit failed: metric=%s error=%s",
                metric_name,
                exc,
            )


def _infer_unit(metric_name: str) -> str:
    if "cost" in metric_name or "usd" in metric_name:
        return "None"
    if "latency" in metric_name or "duration" in metric_name:
        return "Milliseconds"
    if "tokens" in metric_name:
        return "Count"
    if "rate" in metric_name:
        return "Percent"
    return "Count"
