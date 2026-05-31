# Security Guide

## Secrets Management

### Environment Variables

All secrets are loaded from environment variables. Never commit secrets to git.

```bash
# Copy the example file
cp .env.example .env

# Edit with your actual secrets
nano .env
```

### Required Secrets

| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | LLM API access | `sk-...` |
| `DATABASE_PASSWORD` | Database access | `your-secure-password` |
| `API_KEY` | Internal API authentication | `gt-...` |

### Secret Rotation

1. Generate new secret
2. Update `.env` file
3. Restart services: `make dev-down && make dev`
4. Remove old secret from provider dashboard

### Production Deployment

Use a secrets manager:
- AWS: AWS Secrets Manager or Parameter Store
- GCP: Secret Manager
- Azure: Key Vault
- Kubernetes: Sealed Secrets or External Secrets Operator

## Security Checklist

- [ ] `.env` in `.gitignore`
- [ ] No hardcoded secrets in source code
- [ ] Database uses strong password
- [ ] API keys rotated every 90 days
- [ ] HTTPS only in production
- [ ] Rate limiting enabled

## Reporting Vulnerabilities

Contact: security@your-org.com
