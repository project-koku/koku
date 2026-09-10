# CI Triager — Agentic CI Failure Diagnosis

## What it does

An AI agent that monitors failing CI checks on Koku PRs, diagnoses the root cause, and posts **suggested changes** as PR review comments. The developer accepts or rejects each suggestion with one click.

The agent **never pushes commits directly**. It only reads code and posts suggestions.

## Source of truth

| Artifact | Location | Maintained by |
|----------|----------|---------------|
| Agent prompt | [`prompt.md`](prompt.md) | Team (PR) |
| Session bootstrap | [`session-bootstrap.txt`](session-bootstrap.txt) | Team (PR) |
| Konflux setup | [`konflux-setup.md`](konflux-setup.md) | Team (PR) |

**Repo is the source of truth for behavior.** After merging prompt changes, update the scheduled session bootstrap in the runtime environment (see [Runtime setup](#runtime-setup)).

## How it works

```
Scheduled session (every 2 hours at minute 13 — cron: "13 */2 * * *")
  │
  ├── gh pr list --state open (all open PRs from main contributors)
  │
  ├── For each PR with failing checks:
  │     ├── GitHub Actions (Units, Sanity, Codecov) → fetch logs via gh CLI
  │     └── Konflux (build, IQE) → fetch PipelineRun logs via KubeArchive REST API
  │           └── reads last ~100 lines of the IQE pod log (sufficient for pytest summary)
  │
  └── Post result:
        ├── Fixable → PR review with ```suggestion blocks (inline, 1-click apply)
        ├── New file needed → PR comment with full file content
        └── Complex/unknown → PR comment with structured diagnosis
```

## Supported failure types

| Check | What it detects | Agent action |
|-------|----------------|-------------|
| `Units - 3.11` | Assertion mismatch, import errors, missing mocks, typos | Inline suggestion |
| `Sanity` | flake8, black, import ordering, trailing whitespace | Inline suggestion |
| `codecov/patch` | New code with insufficient test coverage | Comment with new test file |
| `Red Hat Konflux / koku-ci / koku` | IQE smoke test failures, build errors, `smokes-required` label blocks | Diagnosis comment with log excerpt |
| (proactive, every PR) | More than 1 new migration file in the PR diff | Warning comment with `squashmigrations` instructions |

**Not in scope:** serializer regressions, complex logic bugs, IQE plugin fixes (private repo), multi-repo changes.

## Runtime setup

### Recommended session prompt (short)

Paste [`session-bootstrap.txt`](session-bootstrap.txt) into the schedule / manual session instead of duplicating the full prompt:

```text
You are the CI Triager for project-koku/koku.

Read and follow every step in:
docs/team_workflows/ci-triager/prompt.md

Use the repo checkout on branch main. Do not improvise steps not in that file.
Post a run summary when finished.
```

This keeps the repo file authoritative and avoids drift from a stale copy in the runtime UI.

### Schedule

- **Session type:** Scheduled — runs every 2 hours at minute 13 (`13 */2 * * *`)
- **Workspace:** `koku` project
- **Branch:** `main`

Configure in the runtime environment (previously Ambient Code UAT; migrating to OpenShell/Hypershell).

### Bot account

- **GitHub user:** `koku-ci-triager-bot`
- **Token type:** Classic PAT, scope `repo`
- **Permissions:** Collaborator (Write) on `project-koku/koku`

The PAT is stored in workspace settings (GitHub integration). No token is committed to the repository.

### Konflux access (cluster Stone)

The agent reads Konflux PipelineRun logs via the **KubeArchive REST API** (PipelineRuns are pruned from the live cluster within minutes of completion and archived to KubeArchive). For each failing `koku-ci` pipeline, the agent fetches the last ~100 lines of the IQE pod log — sufficient to capture the pytest summary (`x failed, y passed`) and error tracebacks.

| Resource | Location |
|----------|----------|
| `kubectl` binary | `/workspace/artifacts/kubectl` (persists between sessions) |
| `kubectl-ka` binary | `/workspace/artifacts/kubectl-ka` (KubeArchive CLI, persists between sessions) |
| Kubeconfig | `/workspace/artifacts/kubeconfig-konflux.yaml` (persists between sessions) |
| SA token | Injected at runtime via `KONFLUX_TOKEN` env var (see below) |
| ServiceAccount | `konflux-bot-0` in namespace `cost-mgmt-dev-tenant` |
| SA permissions | `appstudio-contributor-user-actions` (get/list/watch PipelineRuns) + `ci-triager-taskrun-reader` (TaskRuns, Pods) |
| KubeArchive API | `https://kubearchive-api-server-product-kubearchive.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com` |
| SA manifests | `tenants-config/cluster/stone-prd-rh01/tenants/cost-mgmt-dev-tenant/ci-triager/` in the internal `konflux-release-data` GitOps repo |

### Secrets and environment variables

The `KONFLUX_TOKEN` (Konflux ServiceAccount token) is stored in the workspace as a **Custom Environment Variable**. It is injected automatically into every scheduled session — no manual step required.

To update or rotate the token, generate a new one locally:

```bash
oc login --web
oc create token konflux-bot-0 -n cost-mgmt-dev-tenant --duration=8760h
```

Then paste the output into workspace **Custom Environment Variables → `KONFLUX_TOKEN`**.

## Scope: which PRs are monitored

The agent monitors all **open PRs** authored by the main contributors to `project-koku/koku`:

`bacciotti`, `djnakabaale`, `myersCody`, `lcouzens`, `masayag`, `jordigilh`, `ELK4N4`, `ydayagi`, `pedrolp85`, `dchorvat1`, `esebesto`, `jvcsizilio`, `martinpovolny`

All PR states are covered (draft, ready for review, etc.). The agent skips PRs from other authors.

## Initial setup (new runtime environment)

If the `/workspace/artifacts/` directory is empty (e.g., after workspace reset), run the setup script in a manual session by pasting the contents of [`konflux-setup.md`](konflux-setup.md). It installs `kubectl`, `kubectl-ka`, and rebuilds the kubeconfig using the `KONFLUX_TOKEN` env var already set in Workspace Settings.

## Maintenance

### Updating the agent prompt

Edit [`prompt.md`](prompt.md) via a normal PR. Refresh the session bootstrap in the runtime schedule if needed.

### Renewing the bot PAT

1. Log in to the `koku-ci-triager-bot` GitHub account
2. Settings → Developer settings → Personal access tokens → Tokens (classic)
3. Generate new token with scope `repo`
4. Update the token in workspace settings (GitHub integration)

### Renewing the Konflux SA token

The SA token expires after ~1 year. When it expires:

```bash
oc login --web
oc create token konflux-bot-0 -n cost-mgmt-dev-tenant --duration=8760h
```

Paste the output into workspace **Custom Environment Variables → `KONFLUX_TOKEN`**. No manual session is needed — the new token will be picked up automatically on the next scheduled run.

### Triggering a manual session

Open a manual session with the `koku` workspace and paste or reference [`session-bootstrap.txt`](session-bootstrap.txt).

## Relationship to other agents

| Agent | Role |
|-------|------|
| **CI Triager** (this) | Diagnoses failing CI checks and posts fix suggestions |
| **Agentic PR Labeler** | Proactively applies smoke test labels based on diff analysis |
| **GlitchTip Triager** | Polls GlitchTip and opens draft PRs for safe fixes |

## Guardrails

- Monitors all open PRs from main contributors — never touches PRs from outside the allowed author list
- Never pushes commits, merges PRs, or modifies `.github/`, migrations, serializers, or views
- Maximum suggestion size: ~50 lines — larger fixes result in a diagnosis comment only
- Only reacts to the **most recent** failing run per PR — does not re-triage old runs
- Deduplicates comments: skips if `koku-ci-triager-bot` already commented on the same check after the latest commit

## Future improvements

| Item | Notes |
|------|-------|
| Event-driven trigger | Replace cron schedule with trigger on CI failure |
| GitHub App | Replace machine user with a GitHub App for granular permissions and `[bot]` identity |
| Metrics | Track auto-fix rate, false positives, token cost per session |
