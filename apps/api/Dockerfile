FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# The package includes its internal vendor subset; no sibling checkout or Git URL
# is needed to build the image.
RUN pip install --no-cache-dir ".[postgres,redis,parsers]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
