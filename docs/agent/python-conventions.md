# Python Conventions

Project-specific only — ruff/Black enforce the rest.

- Black line length **119** (see `.pre-commit-config.yaml`)
- Type hints on public functions; prefer f-strings
- Absolute imports from project root (`from masu...`, `from api...`)
- Import order: stdlib → third-party → local (blank line between groups)
- Multiple context managers / patches: `with (patch(...), patch(...)):`
- Prefer specific exception types; put custom exceptions in dedicated `exceptions.py` modules
