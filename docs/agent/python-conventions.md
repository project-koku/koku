# Python Conventions

Project-specific only — ruff/Black enforce the rest.

- Black line length **119** (see `.pre-commit-config.yaml`)
- Type hints on public functions; prefer f-strings
- Absolute imports from project root (`from masu...`, `from api...`)
- Import order: stdlib → third-party → first-party (blank line between groups). **Never hand-sort.** Before every Python commit/push run `pipenv run pre-commit run reorder-python-imports --files <changed.py>`; stage whatever it rewrites. Uppercase constants first is often wrong. See [`.cursor/skills/python-import-order/SKILL.md`](../../.cursor/skills/python-import-order/SKILL.md).
- Multiple context managers / patches: `with (patch(...), patch(...)):`
- Prefer specific exception types; put custom exceptions in dedicated `exceptions.py` modules
