---
description: "Codebase orientation: read key files, show structure, summarize state"
---

# Koku Prime — Codebase Orientation

Read-only warm-up for a new session. Gather context and present a summary.

## Steps

### 1. Read key files
- `CLAUDE.md`
- `README.md` (first 50 lines)

### 2. Project overview

```bash
# Key directories and file counts
for d in koku/api koku/cost_models koku/masu koku/reporting deploy docs; do
  echo "$d: $(find $d -name '*.py' -o -name '*.sql' -o -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ') files"
done
```

### 3. Dev stack status

```bash
docker compose -f docker-compose.yml ps --format '{{.Name}}\t{{.State}}' 2>/dev/null | head -10
```

### 4. Available make targets

```bash
grep '^[a-zA-Z_-]*:' Makefile | head -20
```

### 5. Git status

```bash
git branch --show-current
git log --oneline -5
git status --short | head -10
```

### 6. Available slash commands

```bash
ls .claude/commands/ 2>/dev/null
```

### 7. Present summary

Output a concise orientation report:
- Project: what koku is (1 sentence)
- Branch + recent commits
- Dev stack: which services are up/down
- Key make targets for common tasks
- Available slash commands
- Any warnings (pending migrations, behind remote, etc.)
