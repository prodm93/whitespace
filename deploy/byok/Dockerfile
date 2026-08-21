FROM python:3.11-slim

RUN apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY main.py .
COPY model_registry.yaml .

RUN pip install --no-cache-dir --upgrade setuptools wheel && \
    pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "whitespace.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]
