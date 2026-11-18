---
name: python-import-order
description: >-
  Run Koku reorder-python-imports before committing or pushing Python.
  Use when editing .py files, committing, pushing, opening a PR, fixing Sanity
  CI, pre-commit, flake8, Black, or import order.
---

# Python import order (Koku)

Hand-sorting imports is how Sanity fails. Do not guess. Run the hook.

## Required before every Python commit

Stage only the Python files that belong in the commit. Run the hook on the **index**, not the working tree. `--files` rewrites on-disk files and a later `git add` will commit leftover unstaged edits.

If those files also have unstaged hunks, hide them first:

```bash
git stash push --keep-index -m "python-import-order"
```

Skip the stash when `git status` shows no unstaged Python changes.

Then run the hook:

```bash
pipenv run pre-commit run reorder-python-imports
```

If the hook rewrites files, `git add` **those paths only** while any stash is still applied, and rerun the hook until it passes. An empty index after a later commit is not a substitute for this step.

Lint next, while unstaged edits are still hidden. flake8 reads the working tree, not the index. Exclude deletions; skip when nothing remains:

```bash
files=$(git diff --cached --name-only --diff-filter=ACMR -- '*.py')
[ -n "$files" ] && pipenv run python -m flake8 $files
```

Then restore unstaged work if you stashed:

```bash
git stash pop
```

Do not `git add` those files after a **clean** `stash pop`. If `stash pop` conflicts, the stash is kept. Keep the hook's import order, resolve the file, and `git add` only to clear the unmerged state. Then `git restore --staged -- <path>` for leftover work that should stay unstaged.

Host Python 3.14 breaks the pyupgrade and flake8 **pre-commit envs** (`ast.Str`). `reorder-python-imports` still works. Flake8 must be `pipenv run python -m flake8` (3.11). Do not recreate or run the pre-commit flake8 hook on 3.14.

## Before pushing

The commit workflow above checks the **index**. After a commit the index is usually empty, so running it again does **not** check the commits you are about to push.

If you already ran that workflow on these files before committing, push.

If you skipped it, stash or otherwise hide unrelated work so the tree is clean, then:

```bash
pipenv run pre-commit run reorder-python-imports --from-ref origin/main --to-ref HEAD
files=$(git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.py')
[ -n "$files" ] && pipenv run python -m flake8 $files
```

`--from-ref` still rewrites the working tree. If the hook modifies files, stage them and create a follow-up commit before pushing. Amend only when the user asked to amend, the commit is yours, and it has not been pushed.

## Do not

- Hand-sort `from koku.cache import ...` (uppercase constants first is often **wrong**)
- Assume ASCII or “constants then functions”
- Skip the hook because flake8 passed
- Pass `--files` (that formats the working tree, including unstaged edits)
- `git add` a file the hook rewrote after a clean `stash pop` (that stages restored unstaged work)
- Treat an empty index after commit as a passing push check

## Source of truth

`.pre-commit-config.yaml`: `reorder-python-imports` with `--py3-plus --application-directories koku`.
First-party: `koku`, `api`, `masu`, `reporting`, `sources`, `cost_models`.

Groups: stdlib, third-party, first-party. Blank line between groups. Within a module the hook’s sort wins.
