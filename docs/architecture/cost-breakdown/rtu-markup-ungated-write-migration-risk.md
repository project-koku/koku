# Risk: Ungated Markup RTU Write vs Migration 0352

**Date:** 2026-07-22 (updated 2026-07-24)
**Related:** [`0352_rtu_schema_improvements.py`](../../../koku/reporting/migrations/0352_rtu_schema_improvements.py) (no-op), [`rtu_schema_improvements_operations.py`](../../../koku/reporting/migrations/rtu_schema_improvements_operations.py) (DDL for follow-up 0353), [`rtu-smart-revert-handoff.md`](./rtu-smart-revert-handoff.md)
**Bug:** `populate_markup_rates_to_usage()` ran whenever markup + `cost_model_id` were present, even when Unleash `cost-management.backend.cost_breakdown_rates_to_usage` was OFF.

---

## Summary

The ungated markup → `rates_to_usage` insert is **unlikely to make the RTU schema migration fail** (FK validation). The real risk is **operational**: the migration assumes a quiet/empty RTU table under flag OFF (smart-revert precondition), and ungated markup violates that after truncate and after migrate until a `use_rtu` gate ships.

**Decision (2026-07-24):** Stage already ran the original 0352 DDL. Prod has not. Rather than pausing workers for a destructive prod migrate, **0352 is a no-op in prod** and the original DDL moves to **0353**, released only after the markup RTU gate ([PR #6207](https://github.com/project-koku/koku/pull/6207)) is merged.

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

### What the RTU schema migration does (order matters)

Operations live in [`rtu_schema_improvements_operations.py`](../../../koku/reporting/migrations/rtu_schema_improvements_operations.py) and run via **0353** (not 0352):

1. `TRUNCATE TABLE rates_to_usage`
2. Drop legacy single-column FK indexes; add explicit `ratestousage_rate_id_idx` / `ratestousage_cost_model_id_idx`
3. State-only ORM field updates (`on_delete=CASCADE`, rename `report_period_id` → `report_period`, etc.) — **no DB FK change yet**
4. Recreate composite index `ratestousage_start_src_rp_idx`
5. `RTU_FK_CASCADE_SQL` — rewrite rate/cost_model FKs to `ON DELETE CASCADE`; **add** FKs for `report_period_id` and `source_uuid` if missing
6. Drop duplicate auto-named indexes

Migration header prerequisite: smart revert + Unleash flag OFF (table draining / empty) + markup RTU gate merged.

### Environment state

| Environment | 0352 (no-op) | RTU DDL applied? |
|-------------|--------------|------------------|
| **Stage** | Original 0352 DDL already ran | Yes (via old 0352) |
| **Prod** | Will record no-op 0352 only | No — waits for 0353 |

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

### 3. Inserts after migration has completed (flag OFF, markup still ungated)

| Effect | Details |
|--------|-----------|
| Inserts succeed | New indexes/FKs accept normal markup rows. |
| Invariant broken | Flag OFF no longer means “no RTU writes.” |
| Daily summary / legacy costs | Unaffected (ORM markup + agg excludes markup). |
| Breakdown UI | Low blast radius today if breakdown populate-from-RTU is not wired. |
| CostModel / provider deletes | **Safer** after migration (`ON DELETE CASCADE`) than under older `SET_NULL` / missing FKs. |

**Severity:** Medium (ops / precondition), Low (user-facing cost correctness).

## What this risk is *not*

- Not a dual-write of markup into daily-summary cost-model columns via aggregation.
- Not an AWS/Azure/GCP issue (OCP RTU only).
- Not a high-likelihood hard failure mode for the RTU DDL under the markup insert pattern.

---

# Release Strategy

Migrations run as separate Clowder jobs. Each release pipeline creates a `koku-db-migrate-cji*` pod that runs `migrate_schemas` before app pods roll out.

## Phase A — Smart revert + no-op 0352 (prod, no worker pause)

### Step A1: Release smart revert

Release through the commit prior to the RTU schema migration work, then include the no-op 0352 change:

```
5ae49278a2b382f06e7d0059f3708845f6ce7f67  (smart revert, #6172)
+ no-op 0352_rtu_schema_improvements.py
```

Double-check no other migrations sit between the last prod release and this one.

### Step A2: Run migrate job (prod)

The `koku-db-migrate-cji*` job records `0352_rtu_schema_improvements` in `django_migrations` with **no DDL**. Workers stay up; RTU schema on prod remains at the 0348/0351 shape until Phase B.

**Stage:** Already has the original 0352 DDL applied. Deploying no-op 0352 code does not re-run the migration (already recorded). No action needed.

---

## Phase B — Markup gate + real RTU DDL (0353)

Ship only after [PR #6207](https://github.com/project-koku/koku/pull/6207) (markup RTU Unleash gate) is merged **and** 0353 is added importing [`get_rtu_schema_improvement_operations()`](../../../koku/reporting/migrations/rtu_schema_improvements_operations.py).

### Step B1: Pause RTU writers

RTU writes (including markup, until #6207 is live) only happen in `masu.processor.tasks.update_cost_model_costs` → `CostModelCostUpdater`. That task runs on **CostModelQueue** (summary → OCP chain) and **PriorityQueue** (cost-model API create/update via `CostModelManager`).

#### Must pause (RTU writers)

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

The `ocp_cloud_parquet_summary_updater` calls `_update_markup_cost` directly, which is why summary/ocp workers must pause. Priority workers must pause because cost model API updates enqueue RTU work.

#### Safe to leave up

`download*`, `refresh*`, `hcs`, `subs_*`, API / `masu-server`, and beat do not insert into `rates_to_usage`. Still avoid calling the Masu `update_cost_model_costs` endpoint during the migrate window.

### Step B2: Run migrate job (0353)

Release with `0353_rtu_schema_improvements.py`. The migrate job runs the full RTU DDL on **prod**.

| Environment | Expected outcome |
|-------------|------------------|
| **Prod** | Full DDL runs (truncate, indexes, CASCADE FKs). |
| **Stage** | Schema already matches old 0352. **Fake 0353** on stage: `migrate_schemas --fake reporting 0353` (or equivalent tenant-scoped fake) so the job records 0353 without re-running DDL. |

### Step B3: Release app + spin up workers

After the migrate job succeeds on prod, roll out the app release (markup gate + any other changes) and restore paused workers.

---

## Quick reference

| Phase | Prod migrate job | Worker pause? | RTU DDL on prod |
|-------|------------------|---------------|-----------------|
| A (no-op 0352) | Records 0352, no-op | No | No |
| B (0353 + #6207) | Runs 0353 DDL | Yes | Yes |
