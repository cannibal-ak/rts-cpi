# Secrets Management — RTS CPI

## Overview

The CPI platform handles sensitive credentials for PostgreSQL, RabbitMQ, Redis,
Apache Superset, and tenant-scoped API keys. This document defines how secrets
are generated, stored, rotated, and protected across environments.

---

## Generating Strong Secrets

Use `openssl` or `python` to generate cryptographically random values:

```bash
# 32-byte hex string (64 characters) — suitable for most secrets
openssl rand -hex 32

# URL-safe base64 (43 characters)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Per-Variable Guidance

| Variable | Generation Method | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` | Alphanumeric only (no special chars that break DSNs) |
| `CPI_DATABASE_URL` | Derived from `POSTGRES_PASSWORD` | Update the password segment in the connection string |
| `CPI_DATABASE_URL_RLS` | `openssl rand -hex 24` for `cpi_app` password | Must match the password set in migration 002 |
| `CPI_RABBITMQ_URL` | `openssl rand -hex 16` for RabbitMQ password | Update both RabbitMQ config and this connection string |
| `CPI_REDIS_URL` | `openssl rand -hex 16` if Redis AUTH is enabled | Default local dev uses no password |
| `SUPERSET_SECRET_KEY` | `openssl rand -hex 32` | Flask session signing key — must be stable across restarts |
| `SUPERSET_ADMIN_PASS` | `openssl rand -hex 16` | Change from default immediately in non-dev environments |

---

## Local Development Workflow

1. Copy the template:
   ```bash
   cp .env.example .env
   ```
2. Fill in real values (use the generation commands above or keep dev defaults).
3. Run the stack:
   ```bash
   docker compose up -d
   ```
4. The `.env` file is listed in `.gitignore` and will never be committed.

> **Rule:** Never share `.env` files via Slack, email, or any unencrypted channel.

---

## Production Deployment Options

### Docker Secrets (Docker Swarm / Compose v3.1+)

```yaml
services:
  api:
    secrets:
      - postgres_password
      - superset_secret_key

secrets:
  postgres_password:
    external: true
  superset_secret_key:
    external: true
```

Create secrets:
```bash
echo "your-strong-password" | docker secret create postgres_password -
```

### HashiCorp Vault

1. Store secrets at `secret/data/cpi/production`.
2. Use the Vault Agent sidecar or `envconsul` to inject secrets as environment
   variables at container start.
3. Enable dynamic database credentials for automatic rotation.

### AWS Secrets Manager

1. Store secrets under `/cpi/production/*`.
2. Use the AWS SDK in the API entrypoint to fetch secrets at boot.
3. Enable automatic rotation with Lambda rotation functions.

### Azure Key Vault

1. Store secrets in a dedicated Key Vault instance per environment.
2. Use Managed Identity for zero-credential access from Azure-hosted containers.
3. Reference secrets in Azure Container Apps or AKS via `secretRef`.

---

## Rotation Policy

| Environment | Rotation Frequency | Method |
|---|---|---|
| Local dev | Never (disposable) | Rebuild from `.env.example` |
| Staging | Every 90 days | Manual or Vault dynamic secrets |
| Production | Every 30 days | Automated rotation (Vault / AWS / Azure) |

### Rotation Checklist

1. Generate new secret value.
2. Update the secrets store (Vault / AWS / Azure / Docker secrets).
3. Restart affected services (rolling restart, zero-downtime).
4. Verify connectivity and health checks pass.
5. Revoke the old secret value.
6. Log the rotation event in the audit trail.

---

## What Must NEVER Be Committed

- `.env` files with real credentials
- `*.pem` or `*.key` private key files
- `credentials.json` or service account key files
- Hardcoded passwords, tokens, or API keys in source code
- Database connection strings containing real passwords
- Any file in the `secrets/` directory

The `.gitignore` file is configured to block all of the above. If you suspect a
secret has been committed, rotate it immediately — treat it as compromised.

---

## Emergency: Secret Leaked to Git

1. **Rotate the secret immediately** — do not wait for the commit to be removed.
2. Remove the commit from history:
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   ```
   Or use [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/).
3. Force-push to all remotes (coordinate with the team).
4. Audit access logs for unauthorized usage of the leaked credential.
