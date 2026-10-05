# Write unit tests

You are adding or extending **Python unit tests** in the Koku backend. Follow project conventions exactly; do not weaken assertions or skip failures.

## Scope

- The user will usually have one or more **files open** or selected code paths—treat those as the primary targets. If the target is unclear, infer from selection/active editor and adjacent `test_*.py` modules.

## Before writing tests

1. Read the **code under test** and any existing tests in the same area (`test/` next to the module, or `**/test_*.py`).
2. Decide the correct base class:
   - **`MasuTestCase`** (`masu.test`) — DB fixtures, providers, `self.schema`, OCP/AWS/Azure/GCP test providers.
   - **`IamTestCase`** (`api.iam.test.iam_test_case`) — API tests needing identity, `self.headers`, `self.tenant`.
   - **`django.test.TestCase`** — simple cases without provider/tenant fixtures.
3. For **tenant models** (`reporting`, `cost_models`): wrap queries in `schema_context(self.schema)` or `tenant_context(self.tenant)` as appropriate. Never query tenant tables without context.

## Implementation rules

- Prefer **`model_bakery`** (`baker.make(...)`) for ORM objects over hand-built `create()` unless the test needs very specific fields.
- Use **`subTest()`** for multiple scenarios in one method; avoid `self.skipTest()` inside `subTest` on Python 3.11 (it skips the whole test).
- **Mock external services** not available in unit tests (Trino, Unleash, etc.). **Mock at the import site** used by the code under test (e.g. `patch("masu.database.ocp_report_db_accessor.trino_table_exists", ...)` not a deep util path unless that is what the module imports).
- Use parenthesized context managers for multiple patch context managers: with (patch(...), patch(...)):
- Match existing naming: `test_*.py`, classes `Test*` or `*Test`, methods `test_*` with descriptive names.

## Assertions and quality

- Assert real outcomes: return values, DB state, and mock `assert_called_once` / `assert_called_with` where mocks are used.
- Cover **positive and negative** cases and **edge cases** (empty, None, boundaries) when they matter to the behavior under test.
- Do not add `try/except: pass`, blanket `skipTest`, or vague `assertTrue(True)` to silence failures.

## Running tests (for you or the user)

```bash
pipenv run tox -- path.to.test.module
pipenv run tox -- path.to.test.module.ClassName.test_method_name
```

## Output

- Implement tests in the appropriate `test/` file (new file only if none exists for that module).
- Keep changes **focused** on the requested behavior; no unrelated refactors.
- If the change is large or behavior is ambiguous, state assumptions briefly and proceed with the most consistent pattern in the codebase.
