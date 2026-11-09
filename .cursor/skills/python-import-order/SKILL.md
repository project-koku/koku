---
name: python-import-order
description: >-
  Run Koku reorder-python-imports before committing or pushing Python.
  Use when editing .py files, committing, pushing, opening a PR, fixing Sanity
  CI, pre-commit, flake8, Black, or import order.
---

# Python import order (Koku)

Hand-sorting imports is how Sanity fails. Do not guess. Run the hook.

## Required before every Python commit or push

Stage only the Python files that belong in the commit. Run the hook on the **index**, not the working tree. `--files` rewrites on-disk files and a later `git add` will commit leftover unstaged edits.

If those files also have unstaged hunks, hide them first:

```bash
git stash push --keep-index -m "python-import-order"
pipenv run pre-commit run reorder-python-imports
```

If the hook rewrites files, `git add` **those paths only** while the stash is still applied (they are the only unstaged changes). Then restore unstaged work:

```bash
git stash pop
```

Do not `git add` those files after `stash pop`. Skip the stash when `git status` shows no unstaged Python changes; then `pipenv run pre-commit run reorder-python-imports` is enough.

Also lint the staged files (flake8 does not rewrite):

```bash
pipenv run python -m flake8 $(git diff --cached --name-only -- '*.py')
```

Host Python 3.14 breaks the pyupgrade and flake8 **pre-commit envs** (`ast.Str`). `reorder-python-imports` still works. Flake8 must be `pipenv run python -m flake8` (3.11).

## Do not

- Hand-sort `from koku.cache import ...` (uppercase constants first is often **wrong**)
- Assume ASCII or “constants then functions”
- Skip the hook because flake8 passed
- Pass `--files` (that formats the working tree, including unstaged edits)
- `git add` a file the hook rewrote after `stash pop` (that stages restored unstaged work)

## Source of truth

`.pre-commit-config.yaml`: `reorder-python-imports` with `--py3-plus --application-directories koku`.
First-party: `koku`, `api`, `masu`, `reporting`, `sources`, `cost_models`.

Groups: stdlib, third-party, first-party. Blank line between groups. Within a module the hook’s sort wins.
