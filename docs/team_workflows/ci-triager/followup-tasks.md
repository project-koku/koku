# CI Triager — Follow-up Tasks (COST-7473)

Derived tasks from the initial implementation. Each item below is self-contained and can be picked up independently.

---

## 1. Replace cron schedule with event-driven webhook trigger

**Context:**
The CI Triager currently runs on a fixed cron schedule (`13 */2 * * *`), which means it consumes Ambient Code session resources every 2 hours regardless of whether any PR has a failing check. This generates unnecessary cost and adds up to ~2h of latency between a CI failure and the bot's comment.

**Goal:**
Replace (or complement) the cron schedule with an event-driven trigger using the [`ambient-code/ambient-action`](https://github.com/ambient-code/ambient-action) GitHub Action. The agent would be triggered automatically when a CI check fails on a PR, instead of waiting for the next scheduled window.

**Implementation notes:**
- Add `.github/workflows/ci-triager.yml` to `project-koku/koku`
- Trigger on `check_run` event with `conclusion: failure` or on `pull_request` `synchronize`
- Use `ambient-action` with `api-url`, `api-token`, and `environment-variables: KONFLUX_TOKEN`
- The cron schedule can be kept as a fallback or removed entirely

**Acceptance Criteria:**
- [ ] A GitHub Actions workflow file exists at `.github/workflows/ci-triager.yml`
- [ ] The workflow triggers on CI failure events (not only on a fixed schedule)
- [ ] The bot posts its comment with less than 5 minutes of latency after a check fails
- [ ] No duplicate comments are posted when multiple checks fail simultaneously on the same PR
- [ ] The cron-based fallback (or its removal) is documented in `docs/ci-triager/README.md`

---

## 2. Add Konflux SA token renewal reminder

**Context:**
The CI Triager uses a Konflux ServiceAccount token (`konflux-bot-0`) with `--duration=8760h` (~1 year) to access KubeArchive. When this token expires, the agent loses access to Konflux pipeline logs silently — the only symptom is that Konflux diagnoses stop appearing in PR comments.

**Goal:**
Create a renewal reminder (similar to the one that may already exist for the GitHub bot PAT) so the token is rotated before it expires. Check if the existing bot PAT renewal task/reminder can cover this, or create a separate one.

**Implementation notes:**
- Token was generated in May 2026, expires ~May 2027
- Renewal steps are documented in `docs/ci-triager/README.md` (Maintenance section)
- Renewal only requires: `oc create token konflux-bot-0 -n cost-mgmt-dev-tenant --duration=8760h` + update `KONFLUX_TOKEN` in Ambient Code Workspace Settings

**Acceptance Criteria:**
- [ ] A reminder exists (calendar, Jira task, or automated check) scheduled for ~April 2027
- [ ] The reminder includes the exact renewal steps or a link to `docs/ci-triager/README.md`
- [ ] After renewal, a manual Ambient Code session is run to verify KubeArchive access is restored

---

## 3. Load agent prompt from versioned file in the koku repo

**Context:**
The agent prompt is currently stored in two places: `docs/ci-triager/prompt.md` (GitHub) and copy-pasted into the Ambient Code session/schedule settings. Every prompt change requires a manual update in the Ambient Code UI in addition to the PR.

**Goal:**
Make `docs/ci-triager/prompt.md` the single source of truth. The Ambient Code session prompt becomes a minimal bootstrap that fetches and executes the versioned prompt from GitHub at runtime:

```
Fetch your instructions from the koku repository and follow them exactly:

gh api repos/project-koku/koku/contents/docs/ci-triager/prompt.md --jq '.content' | base64 -d
```

**Implementation notes:**
- No code changes needed — only update the prompt field in the Ambient Code schedule settings
- After this change, prompt updates go through normal PR review and are immediately effective on the next session

**Acceptance Criteria:**
- [ ] The Ambient Code schedule prompt is replaced with the 3-line bootstrap above
- [ ] A manual session is triggered after the change and the agent runs correctly end-to-end
- [ ] The `docs/ci-triager/README.md` "Updating the agent prompt" section is updated to reflect the new workflow: edit `prompt.md` → open PR → merge → effective on next session
- [ ] The full prompt text is no longer stored in Ambient Code settings
