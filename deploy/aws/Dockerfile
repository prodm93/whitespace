FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[saas]"

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ src/
COPY model_registry.yaml .
COPY deploy/aws/lambda/pipeline_orchestrator/handler.py .

ENV MODE=saas

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.handler"]
