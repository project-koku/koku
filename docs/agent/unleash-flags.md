# Agent Guide: Unleash Feature Flags

Compact reference for adding or changing backend Unleash flags. Load when the
task touches feature flags, `masu/processor/__init__.py`, or risky pipeline/SQL
paths.

## Checklist — adding a feature flag

1. Confirm the change needs a flag (risky pipeline/SQL/data path). Additive API-only may skip.
2. Name it as **enablement**: `cost-management.backend.<feature>` (never `disable-*` for rollout).
3. Add a constant (and helper if multi-call-site) in [`koku/masu/processor/__init__.py`](../../koku/masu/processor/__init__.py).
4. Gate with `is_feature_flag_enabled_by_schema(..., dev_fallback=True)`; keep the legacy path.
5. In Unleash UI: flexibleRollout with **stickiness = `schema`** (or `source_uuid` for source-scoped flags).
6. Tests: mock the flag at the **import site**; CI is not `development`, so `dev_fallback=True` stays OFF unless mocked.
7. On-prem: add `ONPREM_FLAG_DEFAULTS` in [`koku/koku/feature_flags.py`](../../koku/koku/feature_flags.py) only if needed.

## Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature enablement | `cost-management.backend.<feature>` or `…enable-<feature>` | `…ocp_gpu_cost_model` |
| Ops kill-switch | `cost-management.backend.disable-<functionality>` | `…disable-summary-processing` |
| Ops classification | descriptive | `…large-customer` |

**Do not** use `disable-*` for new product features. Kill-switches are ops-only.

Source of truth for existing flags: code in `__init__.py` (plus rare inline checks in
`hcs/tasks.py` / `subs/tasks.py`). Do not maintain a markdown inventory.

## When a flag is required

- New/changed SQL INSERT/UPDATE/DELETE in the pipeline
- New pipeline steps or cost-model update flow changes
- New tables, FKs, or FK `on_delete` changes
- Changes to reporting/summary data written

Skip for purely additive API changes that do not affect data processing.

## Code pattern

```python
MY_FEATURE_UNLEASH_FLAG = "cost-management.backend.my_feature_name"

if is_feature_flag_enabled_by_schema(schema, MY_FEATURE_UNLEASH_FLAG, dev_fallback=True):
    # new path
else:
    # legacy path — must remain functional until flag is ON in prod ≥1 billing cycle
```

Prefer a named helper in `__init__.py` when checked from many call sites.

### `dev_fallback` and CI

| Value | Unleash down / unknown |
|-------|------------------------|
| `True` (preferred for new features) | ON only if client `environment` is `development` |
| `False` | Always OFF (rollback-sensitive paths, e.g. RTU) |

CI environment is typically **not** `development` → new path stays **OFF** unless
the test mocks the flag. Mock at the import location used by the code under test:

```python
@patch("masu.database.ocp_report_db_accessor.is_feature_flag_enabled_by_schema", return_value=True)
```

`dev_fallback=True` ≠ ON in production and ≠ ON in CI.

### On-prem

`ONPREM=True` uses `MockUnleashClient`. Set `ONPREM_FLAG_DEFAULTS` only when the
on-prem default must differ from the generic fallback.

## Unleash UI (backend) — stickiness gotcha

App context is usually `{"schema": schema}` (or `{"source_uuid": ...}`).

For flexible/gradual rollout on schema-scoped backend flags:

1. Feature name: `cost-management.backend.<name>`
2. Strategy: flexibleRollout (typical)
3. **stickiness: `schema`** — not `default` / `userId`. Wrong stickiness → flag looks broken even at 100% rollout
4. Optional constraint on context `schema` for selective orgs
5. Enable in stage, then prod

```json
{
  "groupId": "cost-management.backend.my_feature_name",
  "rollout": "100",
  "stickiness": "schema"
}
```

Source-scoped flags: use stickiness / constraints on `source_uuid`.

Local context fields: [`dev/scripts/setup_unleash.py`](../../dev/scripts/setup_unleash.py).

### Frontend (koku-ui)

UI Unleash setup differs (proxy client, context). Do not assume backend
`stickiness: schema`. Coordinate with frontend owners.

## Lifecycle

1. Create code + Unleash UI flag (correct stickiness)
2. Roll out: OFF → selective schemas → stage → prod
3. Keep legacy path ≥1 billing cycle after prod enablement
4. Remove gate, legacy path, constant, on-prem default; archive Unleash feature

## Related

- Always-on: [`CLAUDE.md`](../../CLAUDE.md), [`AGENTS.md`](../../AGENTS.md)
- Scoped rules: [`.cursor/rules/unleash-flags.mdc`](../../.cursor/rules/unleash-flags.mdc), [`.claude/rules/unleash-flags.md`](../../.claude/rules/unleash-flags.md)
- Local Unleash creds: [`../devtools.md`](../devtools.md)
