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

ENV MODE=saas
ENV PORT=8000

EXPOSE ${PORT}

CMD uvicorn whitespace.api.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers ${UVICORN_WORKERS:-2} \
    --timeout-keep-alive 120 \
    --log-level info
