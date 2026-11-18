# RTU Smart Revert — Handoff Document

**Branch:** `smart_revert_rtu`
**Author:** Cody Myers
**Date:** 2026-07-07
**Status:** POC — awaiting team review before PR

---

## What changed

### SQL files (25 restored + 25 new `*_rtu.sql` variants)

Phase 3 (PR #6043) had rewritten all monthly, tag, and VM cost SQL files to write into `rates_to_usage`. This branch reverses that for the original filenames and preserves the Phase 3 content as secondary `*_rtu.sql` files.

**Convention:**
- `monthly_cost_cluster_and_node.sql` — legacy version, writes directly to `reporting_ocpusagelineitem_daily_summary`
- `monthly_cost_cluster_and_node_rtu.sql` — RTU version (Phase 3 content), writes to `rates_to_usage`

**PostgreSQL (`sql/openshift/cost_model/`) — 9 file pairs:**

| Original (legacy, restored) | RTU variant (new) |
|-----------------------------|-------------------|
| `infrastructure_tag_rates.sql` | `infrastructure_tag_rates_rtu.sql` |
| `supplementary_tag_rates.sql` | `supplementary_tag_rates_rtu.sql` |
| `default_infrastructure_tag_rates.sql` | `default_infrastructure_tag_rates_rtu.sql` |
| `default_supplementary_tag_rates.sql` | `default_supplementary_tag_rates_rtu.sql` |
| `monthly_cost_cluster_and_node.sql` | `monthly_cost_cluster_and_node_rtu.sql` |
| `monthly_cost_persistentvolumeclaim.sql` | `monthly_cost_persistentvolumeclaim_rtu.sql` |
| `monthly_cost_persistentvolumeclaim_by_tag.sql` | `monthly_cost_persistentvolumeclaim_by_tag_rtu.sql` |
| `monthly_cost_virtual_machine.sql` | `monthly_cost_virtual_machine_rtu.sql` |
| `node_cost_by_tag.sql` | `node_cost_by_tag_rtu.sql` |

**Trino (`trino_sql/openshift/cost_model/`) — 8 file pairs:**

| Original (legacy, restored) | RTU variant (new) |
|-----------------------------|-------------------|
| `hourly_cost_virtual_machine.sql` | `hourly_cost_virtual_machine_rtu.sql` |
| `hourly_cost_vm_tag_based.sql` | `hourly_cost_vm_tag_based_rtu.sql` |
| `hourly_vm_core.sql` | `hourly_vm_core_rtu.sql` |
| `hourly_vm_core_tag_based.sql` | `hourly_vm_core_tag_based_rtu.sql` |
| `monthly_cost_gpu.sql` | `monthly_cost_gpu_rtu.sql` |
| `monthly_project_tag_based.sql` | `monthly_project_tag_based_rtu.sql` |
| `monthly_vm_core.sql` | `monthly_vm_core_rtu.sql` |
| `monthly_vm_core_tag_based.sql` | `monthly_vm_core_tag_based_rtu.sql` |

**Self-hosted (`self_hosted_sql/openshift/cost_model/`) — same 8 file pairs as Trino.**

Files that were introduced in Phase 2 and have no legacy equivalent are unchanged and remain in the flag-ON path only:
- `sql/openshift/cost_model/usage_rates/insert_usage_rates_to_usage.sql`
- `sql/openshift/cost_model/usage_rates/aggregate_rates_to_daily_summary.sql`
- `sql/openshift/cost_model/usage_rates/insert_markup_rates_to_usage.sql`

---

### `ocp_report_db_accessor.py` — `use_rtu: bool = False` parameter

Five accessor methods now accept a `use_rtu` parameter. When `False` (default) they load the original SQL file; when `True` they load the `*_rtu.sql` variant.

| Method | SQL files selected |
|--------|--------------------|
| `populate_monthly_cost_sql` | `monthly_cost_cluster_and_node[_rtu].sql`, `monthly_cost_persistentvolumeclaim[_rtu].sql`, `monthly_cost_virtual_machine[_rtu].sql`, `monthly_vm_core[_rtu].sql` |
| `populate_tag_cost_sql` | `node_cost_by_tag[_rtu].sql`, `monthly_cost_persistentvolumeclaim_by_tag[_rtu].sql` |
| `populate_vm_usage_costs` | `hourly_cost_virtual_machine[_rtu].sql`, `hourly_vm_core[_rtu].sql` (Trino/self-hosted) |
| `populate_tag_usage_costs` | `infrastructure_tag_rates[_rtu].sql`, `supplementary_tag_rates[_rtu].sql` |
| `populate_tag_usage_default_costs` | `default_infrastructure_tag_rates[_rtu].sql`, `default_supplementary_tag_rates[_rtu].sql` |

The `use_rtu` parameter defaults to `False` so all existing callers outside the orchestrator are unaffected.

---

### `ocp_cost_model_cost_updater.py` — real flag gate restored

`update_summary_cost_model_costs` now branches on the flag value:

**Flag ON — RTU path:**
```
_update_usage_rates_to_usage      → insert_usage_rates_to_usage.sql → rates_to_usage
_update_monthly_cost(use_rtu=True) → monthly_cost_*_rtu.sql          → rates_to_usage
_update_tag_usage_costs(use_rtu=True) → *_tag_rates_rtu.sql          → rates_to_usage
_update_vm_usage_costs(use_rtu=True)  → hourly_*_rtu.sql             → rates_to_usage
_aggregate_rates_to_daily_summary  → reads RTU → daily summary
_update_markup_cost                → ORM UPDATE + insert_markup_rates_to_usage.sql
```

**Flag OFF — legacy path:**
```
_update_usage_costs                → usage_costs.sql                 → daily summary
_update_monthly_cost(use_rtu=False) → monthly_cost_*.sql             → daily summary
_update_tag_usage_costs(use_rtu=False) → *_tag_rates.sql             → daily summary
_update_vm_usage_costs(use_rtu=False)  → hourly_*.sql                → daily summary
(no aggregate step)
_update_markup_cost                → ORM UPDATE on daily summary
```

The private methods `_update_monthly_cost`, `_update_monthly_tag_based_cost`, `_update_node_hour_tag_based_cost`, `_update_tag_usage_costs`, `_update_tag_usage_default_costs`, and `_update_vm_usage_costs` all gained a `use_rtu: bool = False` parameter that threads through to the accessor calls.

---

### `test_phase2_rates_to_usage.py` — orchestration tests updated

- **TC-55** (previously "flag OFF overrides to RTU") — updated to assert the legacy path: `_update_usage_costs` called, `_update_usage_rates_to_usage` and `_aggregate_rates_to_daily_summary` not called.
- **TC-56** (new) — asserts full legacy ordering: `usage → monthly → vm → markup → dist`, no aggregate step.
- **TC-R20-01** — `lambda *a` side effects updated to `lambda *a, **kw` on `mock_monthly` and `mock_vm` (required because those methods now receive `use_rtu=True` as a keyword argument).

---

## How the flag gate works end to end

```
Unleash: cost-management.backend.cost_breakdown_rates_to_usage
         │
         ▼
is_feature_flag_enabled_by_schema(schema, flag, dev_fallback=False)
         │
    ┌────┴────┐
    │ OFF     │ ON
    ▼         ▼
legacy      RTU
path        path
(all SQL    (all SQL
→ daily     → rates_to_usage
 summary)    + aggregate)
```

The flag is evaluated **per tenant schema per billing month** inside `update_summary_cost_model_costs`. With `dev_fallback=False`, if Unleash is unreachable the flag evaluates to `False` (legacy path), which is the safe default.

---

## How to verify locally

**Verify legacy path (flag OFF — default):**
```bash
# Start backend (ONPREM mode for speed)
ONPREM=True docker compose up -d db valkey koku-server masu-server koku-worker koku-beat

# Trigger a cost model resummary
curl "http://localhost:5042/api/cost-management/v1/update_cost_model_costs/?provider_uuid=<UUID>&schema=org1234567"

# Confirm rates_to_usage is empty / not written
docker compose exec db psql -U postgres -d postgres -c \
  "SELECT count(*) FROM org1234567.rates_to_usage;"
# Expected: 0

# Confirm daily summary has cost data
docker compose exec db psql -U postgres -d postgres -c \
  "SELECT sum(cost_model_cpu_cost) FROM org1234567.reporting_ocpusagelineitem_daily_summary
   WHERE cost_model_rate_type IS NOT NULL;"
# Expected: non-zero
```

**Verify RTU path (flag ON — requires Unleash):**
Enable `cost-management.backend.cost_breakdown_rates_to_usage` in Unleash, then run the same resummary. Confirm `rates_to_usage` has rows and daily summary cost rows are rebuilt from them.

---

## What still needs to happen before merging

1. **Team agreement** on the smart revert approach (see [`rtu-issues-and-path-forward.md`](./rtu-issues-and-path-forward.md))
2. **Cost model resummary job** — once deployed with flag OFF, trigger `update_cost_model_costs` for all customers so daily summary is rebuilt from the legacy path and any RTU-only rows are cleaned up
3. **Gap fixes** (in order from [`rates-to-usage-gap-analysis.md`](./rates-to-usage-gap-analysis.md)):
   - GAP-5: index migration on `rate_id` and `cost_model_id` (do this while table is draining — cheaper with fewer rows)
   - GAP-1 + GAP-3: `sync_rate_table` and `PriceListManager` schema context + pre-delete nullification
   - GAP-6 + GAP-7: scoped DELETE before monthly/tag INSERT in `*_rtu.sql` files
   - GAP-2, GAP-4, GAP-8: FK constraint changes and orphan cleanup
4. **Re-enable Unleash flag** on stage after gap fixes are in; validate with real data before rolling out to production

---

## Key files at a glance

| File | Change |
|------|--------|
| `koku/masu/processor/ocp/ocp_cost_model_cost_updater.py` | Real flag gate; `use_rtu` threaded through 6 private methods |
| `koku/masu/database/ocp_report_db_accessor.py` | `use_rtu: bool = False` on 5 accessor methods |
| `koku/masu/database/sql/openshift/cost_model/*.sql` | 9 restored to legacy; 9 `*_rtu.sql` variants added |
| `koku/masu/database/trino_sql/openshift/cost_model/*.sql` | 8 restored to legacy; 8 `*_rtu.sql` variants added |
| `koku/masu/database/self_hosted_sql/openshift/cost_model/*.sql` | 8 restored to legacy; 8 `*_rtu.sql` variants added |
| `koku/masu/test/processor/ocp/test_phase2_rates_to_usage.py` | TC-55 updated; TC-56 added; lambda side effects fixed |
| `docs/architecture/cost-breakdown/rates-to-usage-gap-analysis.md` | Production current state section filled out |
| `docs/architecture/cost-breakdown/rtu-issues-and-path-forward.md` | Smart revert proposal and path forward added |
