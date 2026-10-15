FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# The package includes its internal vendor subset; no sibling checkout or Git URL
# is needed to build the image. Dependency versions come from uv.lock: uv exports
# them as pip constraints, then is removed from the image.
RUN pip install --no-cache-dir uv==0.8.17 \
    && uv export --locked --no-dev --no-emit-project --no-hashes \
        --extra postgres --extra redis --extra parsers \
        --format requirements-txt --output-file /tmp/constraints.txt \
    && PIP_CONSTRAINT=/tmp/constraints.txt \
        pip install --no-cache-dir ".[postgres,redis,parsers]" \
    && pip uninstall -y uv \
    && rm /tmp/constraints.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
