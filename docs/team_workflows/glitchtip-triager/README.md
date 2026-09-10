# GlitchTip Triager — Automated Error Triage

## What it does

An AI agent that **once per week** polls unresolved GlitchTip issues for `insights-hccm-stage`, classifies them, and (when safe) opens a **draft PR** on `project-koku/koku`.

Unlike the CI Triager, this agent **may push branches and open PRs**.

## Source of truth

| Artifact | Location | Maintained by |
|----------|----------|---------------|
| Agent prompt | [`prompt.md`](prompt.md) | Team (PR) |
| Session bootstrap | [`session-bootstrap.txt`](session-bootstrap.txt) | Team (PR) |
| Ignore whitelist | [`ignore-whitelist.yaml`](ignore-whitelist.yaml) | Team (PR) |
| Processed ledger | Workspace artifacts (see below) | Agent (automatic) |

**Repo is the source of truth for behavior.** After merging prompt changes, update the scheduled session bootstrap in the runtime environment (see [Runtime setup](#runtime-setup)).

## Runtime setup

### Recommended session prompt (short)

Paste [`session-bootstrap.txt`](session-bootstrap.txt) into the schedule / manual session instead of duplicating the full prompt:

```text
You are the GlitchTip Triager for project-koku/koku.

Read and follow every step in:
docs/team_workflows/glitchtip-triager/prompt.md

Use the repo checkout on branch main. Do not improvise steps not in that file.
Post a run summary when finished.
```

This keeps the repo file authoritative and avoids drift from a stale copy in the runtime UI.

If the workspace cannot reliably read the repo file, paste the full [`prompt.md`](prompt.md) — but treat the repo copy as canonical and re-sync after each merge.

### Prerequisites (workspace `koku`)

| Item | Where |
|------|--------|
| GitHub bot PAT (`repo` scope, **push allowed**) | Workspace → GitHub integration |
| **Enable auto push** | Workspace settings |
| `GLITCHTIP_BASE_URL` | Custom env var (e.g. `https://glitchtip.devshift.net`) |
| `GLITCHTIP_TOKEN` | Custom env var |
| `GLITCHTIP_ORG` | Custom env var (e.g. `insights`) |
| `GLITCHTIP_PROJECT` | Custom env var (e.g. `insights-hccm-stage`) |

Optional overrides:

| Variable | Default |
|----------|---------|
| `GLITCHTIP_MIN_EVENTS` | `2` |
| `GLITCHTIP_MAX_ISSUES_PER_RUN` | `3` |
| `GLITCHTIP_MAX_PRS_PER_RUN` | `1` |
| `GLITCHTIP_PROCESSED_FILE` | `/workspace/artifacts/glitchtip-processed.json` |

### Schedule

- **Session type:** Scheduled — **once per week**
- **Cron example:** `0 8 * * 1` (Mondays 08:00 UTC — adjust as needed)
- **Workspace:** `koku`
- **Branch:** `main`

Configure in the runtime environment (previously Ambient Code UAT; migrating to OpenShell/Hypershell).

Each weekly run may examine up to 3 issues and open at most 1 draft PR (defaults).

## Processed ledger (`glitchtip-processed.json`)

**Default location:** `/workspace/artifacts/glitchtip-processed.json` in the workspace — **not** committed to this repo.

### Why not commit it to `main`?

| Problem | What happens |
|---------|----------------|
| **Bot commits on `main`** | Every weekly run adds a commit only to update state — noisy history, no human review, blurs "code" vs "automation state". |
| **Needs push without a PR** | The agent would push directly to `main` after each run, bypassing the same review flow you require for real fixes. |
| **Merge conflicts** | Two runs or a human edit touching the same JSON → failed pushes or accidental overwrites. |
| **Wrong tool for the job** | Git tracks **intentional** team changes (prompt, whitelist). Processed IDs are **runtime cache** — like CI logs, not source code. |
| **Weekly schedule + GitHub checks** | With Step 3b (open PR + remote branch), duplicate PRs are caught even if the ledger resets once in a while. |

Committing processed state is a workaround when workspace artifacts do not persist. Prefer fixing artifact persistence; use GitHub duplicate checks as the primary safety net.

| Store in workspace artifacts | Store in repo |
|------------------------------|---------------|
| No bot commits polluting `main` | Visible in git, survives workspace reset |
| Requires artifact persistence between runs | Bot would need to push state commits every run |
| Pair with GitHub duplicate PR checks (primary) | Merge conflicts, review noise |

**Recommendation:** keep the ledger in **workspace artifacts** and ensure the workspace **persists** `/workspace/artifacts/`. Duplicate PR prevention relies primarily on **GitHub pre-flight checks** (open PR, remote branch) documented in [`prompt.md`](prompt.md).

Do **not** commit live processed state to `main`. If persistence is broken, fix workspace storage — do not work around it with weekly JSON commits on `main`.

## Relationship to other agents

| Agent | Role |
|-------|------|
| **GlitchTip Triager** (this) | Polls GlitchTip and opens draft PRs for safe fixes |
| **CI Triager** | Diagnoses failing CI checks and posts fix suggestions |
| **Agentic PR Labeler** | Proactively applies smoke test labels based on diff analysis |

## Guardrails (summary)

- Only project `insights-hccm-stage`.
- Skip issues already in the processed ledger.
- No duplicate PRs for the same GlitchTip issue ID.
- Max **1 draft PR per run** by default (`GLITCHTIP_MAX_PRS_PER_RUN`).
- Draft PRs only; label `smoke-tests`.
- PR scope ≤ 3 files / ~150 lines.

## Maintenance

Update [`prompt.md`](prompt.md) and [`ignore-whitelist.yaml`](ignore-whitelist.yaml) via normal PRs, then refresh the session bootstrap text in the runtime schedule if needed.
