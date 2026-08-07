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
- Migration gate absolute before deploy MR.
- Never self-approve prod MRs.
- Confirm QE/blockers before promoting.

## Steps

1. `bash dev/scripts/release/analyze.sh` → confirm TARGET_SHA + QE clear
2. `bash dev/scripts/release/analyze.sh migrations <TARGET_SHA>` → decision tree
   (PG init vs CJI; Trino always manual)
3. If needed: `prepare-mr.py migration …` → push after approval → `monitor-mr.sh` →
   `monitor.sh db-migration|mgmt-cmd …`
4. `prepare-mr.py deploy …` → push after approval → `monitor-mr.sh`
5. `monitor.sh deploy` → Slack announce when Ready
6. `gen-notes.sh <LAST_TAG> <TARGET_SHA>` → approve Summary → `gh release create`
7. Ask which COST tickets to close

Follow templates and channel names in `docs/agent/production-release.md`.
