# /koku-release — HCCM production release

Orchestrate a koku **production** release with human approval gates.
Full guide: [`docs/agent/production-release.md`](../../docs/agent/production-release.md)

Scripts live in [`dev/scripts/release/`](../../dev/scripts/release/).

## Prerequisites

User must have set `APP_INTERFACE_DIR` (and ideally `APP_INTERFACE_FORK_REMOTE`),
plus optional `GITLAB_PAT` + VPN for MR polling, and `oc` auth for deploy/migration
monitoring. If env is missing, explain Prerequisites from the guide and stop.

## Hard rules

- No git push / `gh release create` without explicit confirmation.
- Migration gate is absolute before deploy MR.
- Never self-approve prod MRs.
- Confirm QE/blockers before promoting.

## Steps

1. `bash dev/scripts/release/analyze.sh` → confirm TARGET_SHA + QE clear
2. `bash dev/scripts/release/analyze.sh migrations <TARGET_SHA>` → decision tree
   (PG: default DBM CJI; Trino always manual; PG+Trino: both before deploy)
3. If migrations needed:
   - PG: `python3 dev/scripts/release/prepare-mr.py migration --target-sha <TARGET_SHA> --type pg`
   - Trino: `python3 dev/scripts/release/prepare-mr.py migration --target-sha <TARGET_SHA> --type trino --command '…'`
   - After approval: push → `bash dev/scripts/release/monitor-mr.sh <branch>`
   - Then: `bash dev/scripts/release/monitor.sh db-migration <7-char> <invocation>`
     or `bash dev/scripts/release/monitor.sh mgmt-cmd <7-char> <invocation>`
4. `python3 dev/scripts/release/prepare-mr.py deploy --target-sha <TARGET_SHA>`
   → push after approval → `bash dev/scripts/release/monitor-mr.sh <branch>`
5. `bash dev/scripts/release/monitor.sh deploy` → Slack announce when Ready
6. `bash dev/scripts/release/gen-notes.sh <LAST_TAG> <TARGET_SHA>` → approve Summary → `gh release create`
7. Ask which COST tickets to close (only tickets in PROD_SHA..TARGET_SHA)

Follow templates and channel names in `docs/agent/production-release.md`.
