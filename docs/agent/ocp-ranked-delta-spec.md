# SPEC — OCP ranked-project delta lookup (Tier 3)

- Spec approval: not obtained (autonomous implementation requested); confidence
  in the completed evidence is correspondingly limited to the scenarios below.
- Setup plan:
  - Isolation: `/Users/mpovolny/Projects/koku/koku-worktrees/ocp-limited-delta`,
    branch `mpovolny/ocp-limited-delta`, so the existing currency-rate PR and
    the user's main checkout are not modified.
  - Tools to install: none; use the repository Python test environment.
  - Git: retain the spec and final evidence in this branch; no checkpoint
    commits until the user requests a PR.
  - Files to add: this spec, a focused test module under
    `koku/api/report/test/ocp/`, and an evidence report under `docs/agent/`.
  - New dependencies: none.

## Failure model

| Failure mode | Protection |
| --- | --- |
| A filtered lookup changes the overall response delta | Assert flag-on and flag-off total delta equality. |
| A returned project loses its previous-period delta | Assert flag-on and flag-off row values/percentages are identical. |
| `NULL` namespace rows are omitted by `IN (...)` | Include a null-project row and assert its delta parity. |
| A category label is used as a namespace | Category requests remain on the legacy path. |
| The feature applies to unrelated report shapes | Assert no-offset, multi-group, non-cost, and CSV shapes retain the legacy path. |
| Unleash is unavailable or disabled | Feature check uses `dev_fallback=True`; flag-off continues to execute the legacy queryset. |

## Scenarios

```gherkin
Feature: bounded previous-period lookups for ranked OCP project reports
  Scenario: Flag-on page lookup is limited without changing deltas
    Given a monthly OCP cost report grouped only by project
      And explicit filter[limit] and filter[offset]
      And more projects exist in the previous period than are returned
    When the tenant-scoped limited-delta flag is enabled
    Then per-project previous totals query only the returned namespaces
      And every response-row delta value and percentage equals the flag-off response
      And the response total delta equals the flag-off response

  Scenario: Null namespace survives the bounded lookup
    Given an eligible ranked report whose selected page contains a null namespace
    When the limited-delta flag is enabled
    Then the previous-period lookup includes the null namespace
      And that row's delta equals the flag-off response

  Scenario: Ineligible report shapes keep the legacy lookup
    Given the flag is enabled
    When a request has no explicit offset, category grouping, multiple groups,
      CSV output, a non-cost report, or a daily resolution
    Then the previous-period per-row lookup remains unfiltered
```

## Must NOT

- Do not change the public request or response contract.
- Do not filter the aggregate used for `total.delta`.
- Do not change non-OCP or non-cost delta reports.
- Do not alter the existing rank/`Others` behavior.
- Do not add indexes, migrations, dependencies, or a global flag default.

## Revisions

- Initial specification derived from the Banco do Brasil timeout request and
  the existing OCP report handler on 2026-09-13.
