FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[saas]"
RUN pip install --no-cache-dir \
    "aws-durable-execution-sdk-python>=1.3,<2" \
    "awslambdaric>=4,<5"

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ src/
COPY model_registry.yaml .
COPY deploy/aws/lambda/pipeline_orchestrator/handler.py \
     deploy/aws/lambda/pipeline_orchestrator/_actions.py \
     deploy/aws/lambda/pipeline_orchestrator/_job_state.py \
     deploy/aws/lambda/pipeline_orchestrator/_loop.py ./

ENV MODE=saas

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.handler"]
