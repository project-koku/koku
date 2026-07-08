---
description: "Health check: verify dev stack, DB, migrations, Python env, and git status"
---

# Koku Doctor — Development Environment Health Check

Run all checks below and present results in a summary table:

```
| Check | Status | Details |
|-------|--------|---------|
```

Use OK / WARN / FAIL for status. For any FAIL, include remediation steps.

## Checks

### 1. Docker/Podman containers

```bash
docker compose -f docker-compose.yml ps --format '{{.Name}}\t{{.State}}\t{{.Ports}}' 2>/dev/null || \
  podman compose -f docker-compose.yml ps 2>/dev/null
```

Expected services: `db` (PostgreSQL), `redis`, `minio`, `koku-server`, `koku-worker`, `koku-listener`.
Optional: `trino`, `hive-metastore`.

FAIL if db/redis/minio are not running. WARN if koku-server or workers are down.

### 2. PostgreSQL

```bash
pg_isready -h localhost -p 15432 -U postgres 2>/dev/null
```

FAIL if not ready. Remediation: `make docker-up-db`

### 3. Redis

```bash
redis-cli -p 6379 ping 2>/dev/null
```

FAIL if no PONG. Remediation: check docker containers.

### 4. Django migrations

```bash
DJANGO_READ_DOT_ENV_FILE=True python koku/manage.py showmigrations --list 2>/dev/null | grep '\[ \]'
```

WARN if pending migrations exist. Show count. Remediation: `make run-migrations`

### 5. Python environment

```bash
which pipenv 2>/dev/null && pipenv --venv 2>/dev/null
python --version 2>/dev/null
```

WARN if pipenv not found or venv doesn't exist. Remediation: `pipenv install --dev`

### 6. .env file

```bash
test -f .env && echo "exists" || echo "missing"
```

WARN if missing. Remediation: `cp .env.example .env`

### 7. Git status

```bash
git fetch --quiet 2>/dev/null
git rev-list --left-right --count HEAD...@{u} 2>/dev/null
git status --porcelain 2>/dev/null | head -5
```

WARN if behind remote. Show ahead/behind counts.

### 8. Pre-commit hooks

```bash
test -f .git/hooks/pre-commit && echo "installed" || echo "not installed"
```

WARN if not installed. Remediation: `pre-commit install`
