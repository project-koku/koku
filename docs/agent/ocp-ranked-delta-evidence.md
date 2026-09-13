# Evidence — OCP ranked-project delta lookup

## Scope

`cost-management.backend.ocp_report_limited_delta` is a tenant-schema scoped
backend feature flag. Configure it default-off in stage and production; the
code uses the repository's `dev_fallback=True` convention. When it is enabled,
only a **monthly OCP cost-by-project** report with an explicit `limit` and
`offset`, exactly one `project` group-by, no category, and non-CSV output
narrows the per-row previous-period delta query to the returned projects.

The response-level previous-period total is intentionally still calculated
from the full prior-period queryset, so its delta is unchanged.

The implementation excludes category reports because their `project` field is
a category-label/namespace `Coalesce`; filtering the table's `namespace` with
those labels could drop rows. It also emits `namespace IS NULL` alongside the
normal `namespace IN (...)` predicate when a selected project is null.

## Automated evidence

Focused suite:

```text
PYTHONPATH=/Users/mpovolny/Projects/koku/koku-worktrees/ocp-limited-delta \
PROMETHEUS_MULTIPROC_DIR=/tmp \
/Users/mpovolny/Projects/koku/koku/.venv/bin/python manage.py test \
api.report.test.ocp.test_limited_delta --no-input -v 1

Ran 6 tests in 0.184s
OK
```

The tests exercise a populated project-summary table and establish:

- complete flag-on response equality with flag-off legacy behavior;
- a bounded previous-period aggregation query;
- preservation of the full aggregate delta through response equality;
- null-project SQL handling;
- legacy behavior for no-offset, daily, multi-group, category, and CSV
  request shapes; and
- the base provider hook's no-op behavior.

Changed-file coverage was collected in that focused run. All new executable
lines are covered; the larger file-level totals include unrelated legacy
paths:

```text
api/report/ocp/query_handler.py  70%
api/report/queries.py            59%
masu/processor/__init__.py       82%
```

Configured pre-commit hooks pass: import ordering, pyupgrade, Black, debug
statement check, whitespace/end-of-file checks, and flake8.

## Mutation probes

The repository has no configured mutation framework. Two temporary manual
mutants were applied and then restored:

| Mutant | Focused-suite result | Killed by |
| --- | --- | --- |
| Return the unfiltered previous queryset | 2 failures | query predicate and null handling tests |
| Remove `not self._category` eligibility guard | 1 failure | category legacy-path test |

## Broader-suite limitation

`api.report.test.ocp.test_ocp_query_handler` currently fails in this local
environment before exercising this change: 50 failures and 2 errors across 87
tests. Its report data fixtures are absent (totals are zero/none) and its GPU
endpoint tests receive 424 because the local RBAC service on port 8111 is not
running. The new focused suite creates its own real project-summary rows and
passes independently.

## Remaining deployment evidence

Create the flag in Unleash as default-off with `schema` stickiness, then enable
it only for the target tenant. Compare flag-off/on latency and response bodies
against the production read replica for the original Banco do Brasil request
before wider rollout. This local work does not measure production RO query
time or create the external Unleash configuration.
