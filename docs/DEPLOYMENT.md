# Deployment Guide

## Prerequisites

- Docker 24+ and Docker Compose v2+
- 2+ CPU cores, 4GB+ RAM minimum
- PostgreSQL 16 with pgvector extension (or use the included Docker image)
- An OpenAI API key or compatible LLM endpoint

## Local Development

```bash
cp .env.example .env
# Edit .env with your API key
make setup
make dev
```

Services:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Database | localhost:5432 |

To stop:

```bash
make dev-down
```

## Production Deployment

### Environment Variables

All configuration is via environment variables. Critical ones for production:

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | Full PostgreSQL connection string | Yes |
| `OPENAI_API_KEY` | API key for LLM and embeddings | Yes |
| `LLM_MODEL` | Model name (default: `gpt-4o-mini`) | No |
| `EMBEDDING_MODEL` | Embedding model name | No |
| `APP_ENV` | Set to `production` | Yes |
| `LOG_LEVEL` | Logging level (recommend `INFO`) | No |

### Secrets Management

- **Never** commit `.env` files to the repository
- Use your platform's secrets manager (AWS Secrets Manager, GCP Secret Manager, etc.)
- Rotate `OPENAI_API_KEY` regularly
- Use strong, unique database passwords

### Resource Sizing

| Component | Min | Recommended |
|---|---|---|
| API | 1 vCPU, 512MB RAM | 2 vCPU, 2GB RAM |
| Frontend | 0.5 vCPU, 256MB RAM | 1 vCPU, 512MB RAM |
| Database | 1 vCPU, 1GB RAM | 2 vCPU, 4GB RAM |

## Cloud Deployment

### AWS ECS (Fargate)

```bash
# Build and push images
docker build -t groundtruth-api ./backend
docker build -t groundtruth-web ./frontend

# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag groundtruth-api:latest <account>.dkr.ecr.<region>.amazonaws.com/groundtruth-api:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/groundtruth-api:latest
```

1. Create an ECS cluster with Fargate launch type
2. Create task definitions for `api` and `web` services
3. Use RDS for PostgreSQL (enable pgvector extension)
4. Configure Application Load Balancer with path-based routing:
   - `/api/*` → API service (port 8000)
   - `/*` → Web service (port 3000)
5. Set environment variables in the task definitions

### GCP Cloud Run

```bash
# Build and push to Artifact Registry
gcloud builds submit --tag gcr.io/<project>/groundtruth-api ./backend
gcloud builds submit --tag gcr.io/<project>/groundtruth-web ./frontend
```

1. Deploy API service:
   ```bash
   gcloud run deploy groundtruth-api \
     --image gcr.io/<project>/groundtruth-api \
     --set-env-vars "APP_ENV=production" \
     --set-secrets "OPENAI_API_KEY=openai-key:latest" \
     --memory 2Gi --cpu 2
   ```
2. Deploy frontend service pointing to the API URL
3. Use Cloud SQL for PostgreSQL with pgvector

### Railway

1. Connect your GitHub repository
2. Create two services: `backend` and `frontend`
3. Add a PostgreSQL plugin (ensure pgvector is available)
4. Set environment variables in the Railway dashboard
5. Railway auto-detects Dockerfiles and deploys on push

## Database Management

### Migrations

```bash
# Run pending migrations
make migrate

# Create a new migration after model changes
make migrate-create msg="add_description_column"
```

Always review auto-generated migrations before applying in production.

### Backups

For production PostgreSQL:

```bash
# Create backup
pg_dump -h <host> -U groundtruth -d groundtruth -F c -f backup_$(date +%Y%m%d).dump

# Restore backup
pg_restore -h <host> -U groundtruth -d groundtruth -c backup_20240115.dump
```

For cloud-hosted databases, use the provider's automated backup feature.

### Scaling

- **Connection pooling**: Use PgBouncer for high-concurrency scenarios
- **Read replicas**: Offload read queries to replicas
- **Vertical scaling**: Increase CPU/RAM for the database instance
- **Vector index**: Consider IVFFlat or HNSW indexes for large document sets

```sql
-- Create HNSW index for faster vector similarity search
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

## Monitoring

### Health Checks

The API exposes a health endpoint:

```bash
curl http://localhost:8000/api/health
```

Response:

```json
{
  "status": "healthy",
  "database": "connected",
  "document_count": 42,
  "version": "0.1.0"
}
```

Configure your load balancer or orchestrator to use this endpoint for health checks.

### Metrics

For production, instrument the API with Prometheus metrics:

- Request count and latency (by endpoint)
- Document processing time
- Embedding generation time
- LLM token usage
- Database connection pool usage

### Logging

Set `LOG_LEVEL=INFO` in production. Logs are structured JSON when `APP_ENV=production`. Use your platform's log aggregation (CloudWatch, Stackdriver, etc.).

## Troubleshooting

### Database Connection Refused

```bash
# Check if the database container is running
docker compose ps db

# Check database logs
docker compose logs db

# Verify connectivity
docker compose exec api python -c "from app.config import get_settings; print(get_settings().DATABASE_URL)"
```

### pgvector Extension Not Available

```bash
# Connect to database and enable extension
docker compose exec db psql -U groundtruth -d groundtruth -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### API Returns 500 on Upload

- Check `OPENAI_API_KEY` is set and valid
- Verify the embedding model is accessible
- Check API logs: `docker compose logs api`

### Frontend Cannot Reach API

- Verify `NEXT_PUBLIC_API_URL` is set correctly
- In Docker, use `http://api:8000` for server-side, `http://localhost:8000` for client-side
- Check CORS configuration in `backend/app/main.py`

### Slow Queries

- Check if vector indexes exist on the `chunks` table
- Monitor database query performance with `pg_stat_statements`
- Consider reducing `CHUNK_SIZE` or adjusting `RETRIEVAL_TOP_K`

### Out of Memory During Ingestion

- Increase container memory limits
- Process documents in smaller batches
- Reduce `EMBEDDING_DIMENSIONS` if using a smaller model
