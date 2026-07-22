# Risk: Ungated Markup RTU Write vs Migration 0352

**Date:** 2026-07-22
**Related:** [`0352_rtu_schema_improvements.py`](../../../koku/reporting/migrations/0352_rtu_schema_improvements.py), [`rtu-smart-revert-handoff.md`](./rtu-smart-revert-handoff.md)
**Bug:** `populate_markup_rates_to_usage()` ran whenever markup + `cost_model_id` were present, even when Unleash `cost-management.backend.cost_breakdown_rates_to_usage` was OFF.

---

## Summary

The ungated markup → `rates_to_usage` insert is **unlikely to make migration 0352 fail** (FK validation). The real risk is **operational**: 0352 assumes a quiet/empty RTU table under flag OFF (smart-revert precondition), and ungated markup violates that after truncate and after migrate until a `use_rtu` gate ships.

---

## Background

### What the missed write does

In `_update_markup_cost`, after the daily-summary ORM markup update (`populate_markup_cost`), the code always called:

```text
populate_markup_rates_to_usage(...)  → insert_markup_rates_to_usage.sql
```

when `_cost_model_id` was set, with **no** `use_rtu` / Unleash check.

Markup RTU rows:

| Field | Value |
|-------|--------|
| `metric_type` | `markup` |
| `rate_id` | `NULL` |
| `cost_model_id` | from updater |
| `source_uuid` / `report_period_id` | from daily summary (`lids`) |
| Aggregation impact | None — aggregate SQL excludes `metric_type = 'markup'` |

Daily-summary markup columns remain correct via the ORM path regardless.

### What 0352 migration does (order matters)

1. `TRUNCATE TABLE rates_to_usage`
2. Drop legacy single-column FK indexes; add explicit `ratestousage_rate_id_idx` / `ratestousage_cost_model_id_idx`
3. State-only ORM field updates (`on_delete=CASCADE`, rename `report_period_id` → `report_period`, etc.) — **no DB FK change yet**
4. Recreate composite index `ratestousage_start_src_rp_idx`
5. `RTU_FK_CASCADE_SQL` — rewrite rate/cost_model FKs to `ON DELETE CASCADE`; **add** FKs for `report_period_id` and `source_uuid` if missing
6. Drop duplicate auto-named indexes

Migration header prerequisite: smart revert + Unleash flag OFF (table draining / empty).

### Current Production State (commit: f623509)

- **Not** yet on smart revert (`#6172`) or 0352 (`#6177`).
- Cost pipeline is still **always-RTU** (flag OFF only warns and still uses RTU).
- Markup RTU writes are consistent with that always-RTU world.
- Risk analysis below applies mainly when **smart revert is live (real flag gate) and 0352 runs with flag OFF**, while markup remains ungated — or when 0352 runs with workers still writing RTU.

---

## Risk analysis

### 1. Pre-existing markup rows at TRUNCATE

| Question | Answer |
|----------|--------|
| Does leftover markup break TRUNCATE? | **No.** Truncate removes all RTU rows, including markup. |
| Impact | Slightly more I/O if the table was not empty; not a correctness failure. |

**Severity:** Low.

### 2. Inserts between TRUNCATE and FK/index fixes

Until `RTU_FK_CASCADE_SQL`, the DB still has 0348-style constraints:

- `rate_id` / `cost_model_id` FKs exist (`SET_NULL`)
- `report_period_id` and `source_uuid` are **not** yet FKs

| Scenario | Outcome |
|----------|---------|
| Insert during `CREATE INDEX` / `ALTER TABLE` | Writer typically **blocks** on locks, then proceeds. |
| Markup insert succeeds in the gap | Rows survive; truncate does **not** run again. |
| Those rows present when new FKs are `ADD CONSTRAINT`’d | Postgres validates all rows. |

**Would markup fail that validation?**

| Column | Markup source | Likely to fail new FK? |
|--------|---------------|-------------------------|
| `rate_id` | `NULL` | No (nullable) |
| `cost_model_id` | live cost model id | Rare (CM deleted mid-flight) |
| `report_period_id` | `lids.report_period_id` (lids already FKs report period) | **No** |
| `source_uuid` | provider UUID being cost-modeled | **Unlikely** (needs missing `TenantAPIProvider` row) |

**Severity for markup specifically:** Low for migrate failure; Medium for “table not empty during index/FK work” (lock waits, slower migrate).

General orphan RTU rows (not markup-shaped) could still fail `ADD CONSTRAINT` — that is not the markup pattern.

### 3. Inserts after 0352 has completed (flag OFF, markup still ungated)

| Effect | Details |
|--------|---------|
| Inserts succeed | New indexes/FKs accept normal markup rows. |
| Invariant broken | Flag OFF no longer means “no RTU writes.” |
| Daily summary / legacy costs | Unaffected (ORM markup + agg excludes markup). |
| Breakdown UI | Low blast radius today if breakdown populate-from-RTU is not wired. |
| CostModel / provider deletes | **Safer** after 0352 (`ON DELETE CASCADE`) than under older `SET_NULL` / missing FKs. |

**Severity:** Medium (ops / precondition), Low (user-facing cost correctness).

## What this risk is *not*

- Not a dual-write of markup into daily-summary cost-model columns via aggregation.
- Not an AWS/Azure/GCP issue (OCP RTU only).
- Not a high-likelihood hard failure mode for 0352’s DDL under the markup insert pattern.

---

# Release Strategy

## Step One: Release Smart Revert

We can release the commit prior the migration:
```
5ae49278a2b382f06e7d0059f3708845f6ce7f67
```

Note: Double check to make sure there are no other migrations that need to be run between our last release and this release.

## Step Two: Turn off workers

After step one is complete, all of the cost model pathways should be disabled except for the markup cost. In order to prevent markup cost rows from being inserted into the RTU table, we will also have to pause workers prior to running the migration.

RTU writes (including markup) only happen in `masu.processor.tasks.update_cost_model_costs` → `CostModelCostUpdater`. That task runs on **CostModelQueue** (summary → OCP chain) and **PriorityQueue** (cost-model API create/update via `CostModelManager`).

### Must pause (RTU writers)

| Deployment | Queue |
|------------|--------|
| `clowder-worker-cost-model` | `cost_model` |
| `clowder-worker-cost-model-xl` | `cost_model_xl` |
| `clowder-worker-cost-model-penalty` | `cost_model_penalty` |
| `clowder-worker-priority` | `priority` |
| `clowder-worker-priority-xl` | `priority_xl` |
| `clowder-worker-priority-penalty` | `priority_penalty` |
| `clowder-worker-summary` (+ `-xl`, `-penalty`) | `summary*` |
| `clowder-worker-ocp` (+ `-xl`, `-penalty`) | `ocp*` |

The `ocp_cloud_parquet_summary_updater` calls `_update_markup_cost` directly which is why we would have to pause the summary/ocp workers.

We pause the priority workers because they trigger when customers make cost model updates.

### Also recommended (Stop feeding the backlog.)

These do not write RTU themselves, but they enqueue `update_cost_model_costs`, which will fire as soon as writer workers return:

| Deployment | Queues |
|------------|--------|


### Safe to leave up

`download*`, `refresh*`, `hcs`, `subs_*`, API / `masu-server`, and beat do not insert into `rates_to_usage`. Still avoid calling the Masu `update_cost_model_costs` endpoint during the migrate window.

## Step Three: Migration

Run the migration in production, we have disabled the workers that could potentially write to the RTU table as the migration is running

## Step Four: Release & Spin up workers

After the migration is complete, we can release [the fix](https://github.com/project-koku/koku/pull/6207) for the missed markup & spin the workers back up to start processing data again.
