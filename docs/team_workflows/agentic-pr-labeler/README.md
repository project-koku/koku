# Agentic PR Labeler — Automated Smoke Test Label Management

## What it does

An AI agent that monitors open Koku PRs, analyzes the diff, and **automatically applies** the appropriate smoke test label when `smokes-required` is present without a specific smoke label, or when `koku-ci` is blocked at the init phase.

Unlike the CI Triager, this agent **applies labels** (via `gh pr edit`) in addition to posting explanatory comments. It **never pushes commits**.

**Pilot scope:** only PRs authored by `dchorvat1`.

## Source of truth

| Artifact | Location | Maintained by |
|----------|----------|---------------|
| Agent prompt | [`prompt.md`](prompt.md) | Team (PR) |
| Session bootstrap | [`session-bootstrap.txt`](session-bootstrap.txt) | Team (PR) |

**Repo is the source of truth for behavior.** After merging prompt changes, update the scheduled session bootstrap in the runtime environment (see [Runtime setup](#runtime-setup)).

## How it works

```
Scheduled session
  │
  ├── gh pr list --state open (pilot author only)
  │
  ├── For each PR with smokes-required but no specific smoke label:
  │     ├── Analyze diff (providers, scope, dual-path SQL)
  │     └── Apply label via gh pr edit
  │
  └── Post PR comment explaining label choice
```

## Runtime setup

### Recommended session prompt (short)

Paste [`session-bootstrap.txt`](session-bootstrap.txt) into the schedule / manual session instead of duplicating the full prompt:

```text
You are the Agentic PR Labeler for project-koku/koku.

Read and follow every step in:
docs/team_workflows/agentic-pr-labeler/prompt.md

Use the repo checkout on branch main. Do not improvise steps not in that file.
Post a run summary when finished.
```

This keeps the repo file authoritative and avoids drift from a stale copy in the runtime UI.

### Bot account

- **GitHub user:** `koku-ci-triager-bot` (shared with CI Triager)
- **Token type:** Classic PAT, scope `repo`
- **Permissions:** Collaborator (Write) on `project-koku/koku`

The PAT is stored in workspace settings (GitHub integration). No token is committed to the repository.

### Schedule

Configure in the runtime environment (previously Ambient Code UAT; migrating to OpenShell/Hypershell).

## Scope: which PRs are managed

**Pilot:** only PRs authored by `dchorvat1`. All PR states are covered (draft, ready for review, etc.). The agent skips PRs from other authors.

To expand scope after the pilot, update `ALLOWED_AUTHORS` in [`prompt.md`](prompt.md) via a normal PR.

## Relationship to other agents

| Agent | Role |
|-------|------|
| **Agentic PR Labeler** (this) | Proactively applies smoke test labels based on diff analysis |
| **CI Triager** | Diagnoses failing CI checks and posts fix suggestions |
| **GlitchTip Triager** | Polls GlitchTip and opens draft PRs for safe fixes |

The GitHub workflow [`.github/workflows/pr-labeler.yml`](../../../.github/workflows/pr-labeler.yml) adds `smokes-required` / `ok-to-skip-smokes` automatically. This agent adds the **specific** smoke test label required by Konflux.

## Maintenance

Update [`prompt.md`](prompt.md) via normal PRs, then refresh the session bootstrap text in the runtime schedule if needed.

### Renewing the bot PAT

1. Log in to the `koku-ci-triager-bot` GitHub account
2. Settings → Developer settings → Personal access tokens → Tokens (classic)
3. Generate new token with scope `repo`
4. Update the token in workspace settings (GitHub integration)

## Guardrails

- Never pushes commits, merges PRs, or modifies `.github/`, migrations, serializers, or views
- Only manages labels when `smokes-required` is present without a specific smoke label, or `koku-ci` init fails
- Deduplicates: skips if `koku-ci-triager-bot` already commented after the latest commit
- Always posts a PR comment explaining the label choice
