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

On every changed `.py` file:

```bash
pipenv run pre-commit run reorder-python-imports --files <changed.py files>
```

If the hook reports `files were modified`, those files are now correct. Stage them. Do not revert the reorder. Re-run until the hook passes.

Also run:

```bash
pipenv run python -m flake8 <changed.py files>
```

Host Python 3.14 breaks the pyupgrade and flake8 **pre-commit envs** (`ast.Str`). `reorder-python-imports` still works. Flake8 must be `pipenv run python -m flake8` (3.11).

## Do not

- Hand-sort `from koku.cache import ...` (uppercase constants first is often **wrong**)
- Assume ASCII or “constants then functions”
- Skip the hook because flake8 passed
- Commit with unstaged reorder-python-imports edits

## Source of truth

`.pre-commit-config.yaml`: `reorder-python-imports` with `--py3-plus --application-directories koku`.
First-party: `koku`, `api`, `masu`, `reporting`, `sources`, `cost_models`.

Groups: stdlib, third-party, first-party. Blank line between groups. Within a module the hook’s sort wins.
