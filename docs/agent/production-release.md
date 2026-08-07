# Production release (HCCM / koku)

On-demand guide for promoting koku to **production** via app-interface.
Stage auto-deploys on merge to `main`. Production is a manual two-step process
(migrations if needed → deploy `ref`).

Human ops detail (Ibutsu criteria, known issues, screenshots) lives in the
team service-docs: `operations/release-process.md`.

**Scripts:** [`dev/scripts/release/`](../../dev/scripts/release/)
**Cursor skill:** [`.cursor/skills/koku-release/SKILL.md`](../../.cursor/skills/koku-release/SKILL.md)
**Claude command:** [`.claude/commands/koku-release.md`](../../.claude/commands/koku-release.md)
**Release notes UI flow:** [`docs/generating-release-notes.md`](../generating-release-notes.md)

---

## Prerequisites (one-time per engineer)

1. **app-interface** clone + **your GitLab fork** with a push remote:
   ```bash
   git -C "$APP_INTERFACE_DIR" remote add my-fork \
     git@gitlab.cee.redhat.com:<user>/app-interface.git
   ```
2. Export (shell profile or session):
   ```bash
   export APP_INTERFACE_DIR=~/development/app-interface   # your path
   export APP_INTERFACE_FORK_REMOTE=my-fork                # optional if auto-detect works
   ```
3. Optional: `export GITLAB_PAT=…` (GitLab CEE, scope `api`) + VPN — enables
   automatic MR polling. Without it, scripts fall back to manual steps.
4. `oc` authenticated to prod (via `koku-ci/koku-ci-management`: `make login`,
   `eval $(make env)`).
5. Tools: `gh`, `git`, `python3`, `curl`.

`KOKU_DIR` defaults to this repository root (detected from the scripts).

---

## Hard rules

- **Never** push, merge, self-approve, or run `gh release create` without
  explicit human confirmation.
- **Migration gate is absolute:** no deploy MR while a migration MR is open or
  the migration job is still running.
- **Never self-approve** production MRs. Wait for `/lgtm` → `app-sre-bot` merge.
- Confirm QE / known blockers before promoting (Ibutsu / team channels).

---

## Flow overview

```
[choose SHA + QE clear]
       ↓
[check migrations]
       ↓
[if PG and/or Trino] CJI migration MR(s) → monitor job success
       ↓
[required] Deploy MR (ref → TARGET_SHA) → monitor pods
       ↓
[prod] Slack announce → GitHub release notes → close Jira
```

PG: default to DBM CJI before deploy (team practice). Trino: always MGMT CJI.
### Migration decision tree

```
No migrations
  → deploy MR only

PG Django migrations (team practice: almost always manual CJI)
  → Default: migration MR (DBM_IMAGE_TAG + DBM_INVOCATION) → monitor → deploy MR
  → Confirm with the migration author that the CJI is appropriate / already planned.
  → Rare exception: author says init container alone is enough → deploy MR only

Trino migrations (ALWAYS manual CJI)
  → Ask for full migrate_trino_tables command
  → migration MR → monitor → deploy MR
```

Note: pods still have an init-container migrate path, but **production releases in this
team almost always run PG via the DBM ClowdJobInvocation first**, then promote `ref`.
---

## Scripts

Run from the koku repo root (or any cwd; scripts resolve paths via env / detection).

| Step | Command |
|------|---------|
| Readiness report | `bash dev/scripts/release/analyze.sh` |
| Migration check | `bash dev/scripts/release/analyze.sh migrations <TARGET_SHA>` |
| Prepare deploy branch | `python3 dev/scripts/release/prepare-mr.py deploy --target-sha <SHA>` |
| Prepare PG migration | `python3 dev/scripts/release/prepare-mr.py migration --target-sha <SHA> --type pg` |
| Prepare Trino migration | `python3 dev/scripts/release/prepare-mr.py migration --target-sha <SHA> --type trino --command '…'` |
| Monitor MR | `bash dev/scripts/release/monitor-mr.sh <branch>` |
| Monitor deploy pods | `bash dev/scripts/release/monitor.sh deploy` |
| Monitor PG CJI | `bash dev/scripts/release/monitor.sh db-migration <7-char> <invocation>` |
| Monitor Trino CJI | `bash dev/scripts/release/monitor.sh mgmt-cmd <7-char> <invocation>` |
| Draft release notes | `bash dev/scripts/release/gen-notes.sh <LAST_TAG> <TARGET_SHA>` |

`prepare-mr.py` creates the local branch/commit only. It prints the push command
and MR URL — **do not push until the human approves**.

---

## Conventions

| Item | Format |
|------|--------|
| Migration branch | `hccm-prod-migrations-<7-char-sha>` |
| Deploy branch | `hccm-prod-<7-char-sha>` |
| Migration commit | `hccm: promote <7-char-sha> migrations to prod` |
| Deploy commit | `hccm: promote <7-char-sha> to prod` |
| Image tags | First 7 chars of target SHA |
| Re-run CJI | Increment `DBM_INVOCATION` / `MGMT_INVOCATION` |
| Deploy file | `data/services/insights/hccm/deploy-clowder.yml` (prod block) |
| Safe SHA | Prefer `make get-release-commit` / `dev/scripts/get-release-commit.py` |

Prod fields (as needed): `ref`, `DBM_IMAGE_TAG`, `DBM_INVOCATION`,
`MGMT_IMAGE_TAG`, `MGMT_INVOCATION`, `MGMT_COMMAND`.

Best practice before merging the deploy MR: Celery queues empty.

---

## Post-release (prod only)

1. `#cost-mgmt-sre`:
   `@crc-cost-mgmt-dev The latest release of cost-management to production has finished. Any new alerts should be investigated. Release notes will follow in the team chat when completed.`
2. Create GitHub release (`gen-notes.sh` + [`generating-release-notes.md`](../generating-release-notes.md)).
3. `#forum-cost-mgmt`: announce with release URL.
4. Close Jira COST tickets that shipped in the release (confirm with human).

Review channel for MRs: `#crc-cost-mgmt-sre` → `@crc-cost-mgmt-dev`.
