---
name: koku-release
description: Orchestrates the Koku (HCCM) production release with human approval gates. Use when the user says "release", "fazer release", "release do koku", "promover para prod", or asks to start the production release process.
---

# Koku Release Orchestrator

Reduces manual effort on the HCCM production release. Human decisions are required only at explicit gates.

**Guide:** [`docs/agent/production-release.md`](../../docs/agent/production-release.md)
**Scripts:** [`dev/scripts/release/`](../../dev/scripts/release/)

**Env (per engineer):** `APP_INTERFACE_DIR`, optional `APP_INTERFACE_FORK_REMOTE`, optional `GITLAB_PAT`. See the guide Prerequisites.

---

## Hard rules

- **NEVER run write operations** (git push, gh release create) without explicit user approval.
- Before every write, show what will change and ask for confirmation — wait.
- **Migration gate is absolute:** no deploy MR while any migration MR is pending or being monitored.
- **Never self-approve** the MR. Wait for the user to confirm `/lgtm` and merge.
- GitLab CEE API needs **VPN** + `GITLAB_PAT`. Push via SSH often works without VPN.

---

## Step 1 — Release Readiness Report

```bash
bash dev/scripts/release/analyze.sh
```

Present the full report. Ask which commit to release (suggest the reported SHA).
Record `TARGET_SHA`. Do not proceed until confirmed.

Then ask whether QE / known blockers are clear. Do not proceed until confirmed.

---

## Step 2 — Migration Gate (before any deploy MR)

```bash
bash dev/scripts/release/analyze.sh migrations <TARGET_SHA>
```

Decision tree — do not skip or reorder:

```
No migrations → Step 3

PG migrations → default to manual CJI (DBM_*) — team practice (~always)
  Confirm with migration author, then Step 2A → 2B → Step 3
  Rare: author says init container alone is enough → Step 3

Trino (ALWAYS manual) → ask for full migrate_trino_tables command
  → Step 2A → 2B → Step 3
```
### Step 2A — Create migration MR

Announce in `#crc-cost-mgmt-sre` before proceeding.

```bash
# PG
python3 dev/scripts/release/prepare-mr.py migration --target-sha <TARGET_SHA> --type pg

# Trino
python3 dev/scripts/release/prepare-mr.py migration --target-sha <TARGET_SHA> --type trino \
  --command "<full migrate_trino_tables command>"
```

After approval, run the printed `git push <fork-remote> <branch>`, open the MR URL,
request review. Then:

```bash
bash dev/scripts/release/monitor-mr.sh <branch>
```

Wait for merge confirmation before continuing.

### Step 2B — Monitor migration job

```bash
bash dev/scripts/release/monitor.sh db-migration <7-char-sha> <DBM_INVOCATION>
# or
bash dev/scripts/release/monitor.sh mgmt-cmd <7-char-sha> <MGMT_INVOCATION>
```

Announce success in `#crc-cost-mgmt-sre`. Only then Step 3.

---

## Step 3 — Deploy MR

```bash
python3 dev/scripts/release/prepare-mr.py deploy --target-sha <TARGET_SHA>
```

After approval: push, open MR, post Slack from the analyze report, monitor MR.
Wait for merge before Step 4.

---

## Step 4 — Monitor deploy

```bash
bash dev/scripts/release/monitor.sh deploy
```

When pods are Running/Ready, announce in `#cost-mgmt-sre` (see guide).

---

## Step 5 — Release notes

```bash
bash dev/scripts/release/gen-notes.sh <LAST_TAG> <TARGET_SHA>
```

Draft Summary for the user; after approval run the printed `gh release create`.
User finalizes pre-release → latest on GitHub. Announce in `#forum-cost-mgmt`.

---

## Step 6 — Close Jira tickets

List COST tickets from the analyze report. Ask which to close; only transition
tickets the user approves.
