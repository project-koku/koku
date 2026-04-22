# Cursor Slash Commands

These shared slash commands help with common Koku review and PR workflows.

## How To Use

1. Open Cursor chat in this repository.
2. Type `/` and select one of these commands.
3. Give any missing context (PR number, branch, changed files, etc.).
4. Review the generated output before acting on it.

## Available Commands

### `architect`
- **Use when:** You have a PRD (or epic/RFC) and want **architecture docs** under `docs/architecture/`—codebase map, API/system design draft, and a **builder handoff**—without implementing feature code.
- **Output:** A structured doc package (hub `README.md` ± sibling `.md` files) following [`docs/architecture/README.md`](../../docs/architecture/README.md), plus explicit IQ/decisions and links into `koku/`.
- **How:** Type `/architect` in chat, attach or paste the PRD, and provide `feature slug`, epic key, and desired hub depth (lean / standard / full). See the command file for boundaries and workflow.

### `address-github-pr-comments`
- **Use when:** You want to work through reviewer comments on a PR end-to-end.
- **Output:** A structured workflow for triaging comments, applying fixes, testing, and replying.

### `code-review-checklist`
- **Use when:** You want a thorough review checklist before approving or merging code.
- **Output:** A comprehensive checklist covering functionality, quality, testing, security, docs, and more.

### `create-pr-testing-instructions`
- **Use when:** You need to write PR testing instructions in the Koku format.
- **Output:** A templated `Jira / Description / Testing / Release Notes` section with guidance.

### `light-review-existing-diffs`
- **Use when:** You want a quick first-pass review of current diffs.
- **Output:** A lightweight checklist for obvious correctness, style, and test/doc gaps.

## Suggested Usage Pattern

- Start with `light-review-existing-diffs` for fast signal.
- Follow with `code-review-checklist` for deeper review.
- Use `create-pr-testing-instructions` when finalizing the PR description.
- Use `address-github-pr-comments` after reviewer feedback arrives.

## Notes

- These commands are guidance templates, not hard rules.
- Keep project standards in `.cursorrules` as the source of truth.
- If a command output conflicts with current team conventions, follow team conventions.
