# RatesToUsage (RTU) — Known issues and path forward

**Status:** Draft (crowdsource)
**Owner:** Victor Sizilio (initial); Cody Myers (gap analysis)
**Created:** 2026-07-07
**Context:** Cost breakdown / Phase 2 work paused at stakeholder level; team resetting on RTU logic before more tactical fixes.

## Purpose

This document collects what we know about problems with the `rates_to_usage` table and related flows. Goal: agree on the full picture, then choose a coherent path forward — not a series of one-off PRs per Glitchtip alert.

**This is a living doc.** Add findings, corrections, and open questions. Do not treat anything here as fully validated unless marked confirmed.

## Cody's gap analysis

Cody's detailed analysis lives in **[rates-to-usage-gap-analysis.md](./rates-to-usage-gap-analysis.md)** (branch `gap_analysis`). It documents seven gaps (GAP-1–GAP-7) with root causes, proposed fixes, and affected files.

Rough mapping to the issue inventory below (not 1:1 — Cody's doc may add or refine items):

| This doc | Cody's gap |
|----------|------------|
| Issue #1 (COST-7736) | [GAP-1](./rates-to-usage-gap-analysis.md#gap-1-sync_rate_table-deletes-rate-rows-still-referenced-by-rates_to_usagerate_id) |
| Issue #2 (cost model delete) | [GAP-2](./rates-to-usage-gap-analysis.md#gap-2-cost-model-deletion-doesnt-null-rates_to_usagecost_model_id-reliably) — *note: proposes CASCADE, not null-before-delete* |
| Issue #7 (price list delete) | [GAP-3](./rates-to-usage-gap-analysis.md#gap-3-price-list-deletion-cascades-to-rate-deletion--same-fk-hazard-as-gap-1) |
| — | [GAP-4](./rates-to-usage-gap-analysis.md#gap-4-report_period_id-is-a-bare-integerfield--no-fk-no-automatic-cascade-on-deletion) (`report_period_id` orphans) |
| Issue #5 (missing index) | [GAP-5](./rates-to-usage-gap-analysis.md#gap-5-missing-indexes-on-rate_id-and-cost_model_id-for-fk-set_null-lookups) |
| — | [GAP-6](./rates-to-usage-gap-analysis.md#gap-6-monthly-cost-sql-inserts-rtu-rows-without-a-preceding-delete), [GAP-7](./rates-to-usage-gap-analysis.md#gap-7-tag-usage-cost-sql-inserts-rtu-rows-without-a-preceding-delete) (pipeline duplicate RTU rows) |

Issues **#3–#4** (INSERT race) and **#6** (root cause) are not fully covered there yet — keep tracking here until aligned.

Organization of these two docs is TBD; Cody may consolidate or restructure after review.

## Background (short)

- **Phase 2** (PR #6017, May 2026) introduced `rates_to_usage` — per-rate cost rows from the cost model SQL pipeline, partitioned by `usage_start`.
- Rows can reference `cost_model_rate` (`rate_id`) and `cost_model` (`cost_model_id`).
- Phase 2 also started **populating those FKs** in pipeline INSERTs (previously mostly NULL).
- **Cost breakdown UI work is paused**; we still need RTU to be stable and not block cost model API operations.

## What triggered this pause

While fixing [COST-7736](https://redhat.atlassian.net/browse/COST-7736) (cost model PUT fails with FK violation when removing a rate), review surfaced:

- The same class of FK errors on **other code paths** (not only PUT / rate delete).
- **Performance risk** for large tenants if we null `rate_id` without an index (seq scan on partitioned table inside `@transaction.atomic`).
- **Unclear root cause** — why Django `on_delete=SET_NULL` does not appear to prevent the error in production.

Tactical fix (PR #6166) may be correct for one symptom; team agreed to **pause and reset** on broader RTU logic.

---

## Issue inventory (crowdsource)

Severity: **Confirmed** (Glitchtip/prod or stage) | **Likely** (code review) | **Open** (needs investigation)

### 1. DELETE rate while RTU still references `rate_id` (COST-7736)

| | |
|---|---|
| **Symptom** | HTTP 500 on `PUT /cost-models/{uuid}/` when removing a rate |
| **Error** | `update or delete on table "cost_model_rate" violates FK ... rates_to_usage_rate_id_...` |
| **Path** | `CostModelSerializer.update` → `CostModelManager.update` → `sync_rate_table()` → `Rate.delete()` |
| **Evidence** | Glitchtip **PROD-5ER** (5 events, last seen 2026-06-29) |
| **Proposed fix** | Null `rates_to_usage.rate_id` before deleting stale `Rate` rows (PR #6166) |
| **Status** | Fix drafted; **implementation paused** pending broader plan |
| **Notes** | Started after Phase 2 populated `rate_id` on RTU rows |

### 2. DELETE cost model while RTU still references `cost_model_id`

| | |
|---|---|
| **Symptom** | HTTP 500 on `DELETE /cost-models/{uuid}/` |
| **Error** | `update or delete on table "cost_model" violates FK ... rates_to_usage_cost_model_id_...` |
| **Path** | `CostModelViewSet.destroy` |
| **Evidence** | Glitchtip **STAGE-5I4** (stage); bot draft PR #6159 |
| **Proposed fix** | Null `rates_to_usage.cost_model_id` before delete (same pattern as #1) |
| **Status** | Likely same class as #1; separate PR/ticket |

### 3. Pipeline INSERT with stale `rate_id` (race)

| | |
|---|---|
| **Symptom** | Worker/pipeline fails during RTU INSERT |
| **Error** | `insert or update on table "rates_to_usage_*" violates FK ... rate_id ... not present in cost_model_rate` |
| **Path** | `masu` cost model updater → raw SQL INSERT into `rates_to_usage` |
| **Evidence** | Glitchtip **PROD-5F9** (5 events, prod) |
| **Cause (hypothesis)** | Rate deleted (or sync removed it) while Celery job still INSERTs with old `rate_id` |
| **Status** | **Mitigated by smart revert** — RTU INSERT does not run with flag OFF; will recur if flag re-enabled before GAP-1/GAP-3 are fixed |
| **Notes** | Different direction than #1 (INSERT vs DELETE) |

### 4. Pipeline INSERT with stale `cost_model_id` (race)

| | |
|---|---|
| **Symptom** | Same as #3 but on `cost_model_id` |
| **Evidence** | Glitchtip **STAGE-5HI** (9 events, stage) |
| **Status** | **Mitigated by smart revert** — same reasoning as #3 |

### 5. Missing index on `rates_to_usage.rate_id`

| | |
|---|---|
| **Symptom** | Slow cost model updates (or timeout HTTP 500) for large tenants |
| **Cause** | `UPDATE ... WHERE rate_id IN (...)` without index → seq scan across partitions |
| **Context** | Runs inside `CostModelManager.update()` `@transaction.atomic` — user waits for full transaction |
| **Evidence** | Production row counts (Martin, 2026-07-07): ~15.6M rows total; 3 tenants 1M+ (up to ~5.3M); 97% tenants have 0 rows |
| **Status** | Likely; needs validation on whale tenants |
| **Mitigation** | Index on `rate_id` (and possibly `cost_model_id` if we null on delete path) |

### 6. Root cause of FK failures unclear

| | |
|---|---|
| **Question** | Why does `on_delete=SET_NULL` not prevent #1/#2 automatically? |
| **Hypotheses** | (a) Partitioned table + DEFERRABLE FK at DB level; (b) Django Collector vs PostgreSQL enforcement gap; (c) custom partition manager / trigger propagation; (d) DB constraint not actually `ON DELETE SET NULL` |
| **Status** | Partially addressed — [GAP-1](./rates-to-usage-gap-analysis.md#gap-1-sync_rate_table-deletes-rate-rows-still-referenced-by-rates_to_usagerate_id) identifies missing `schema_context` in `sync_rate_table()` as root cause for #1; #2 may differ |
| **Reference** | [PR 6166 adversarial review](https://github.com/project-koku/koku/blob/pr-6166-adversarial-review/pr-6166-review.md) (leads only — verify claims); [Cody's gap analysis](./rates-to-usage-gap-analysis.md) |

### 7. Same class on other delete paths (unconfirmed)

| | |
|---|---|
| **Examples** | PriceList delete → CASCADE to `Rate` → SET_NULL on RTU; other partitioned FKs |
| **Status** | Likely from code inspection; no Glitchtip hit cited yet |

### 8. Broader design tension (Phase 2)

| | |
|---|---|
| **Topic** | RTU rows now hold real `rate_id` / `cost_model_id`, but delete/sync paths were built when FKs were mostly NULL |
| **Policy** | SET NULL (keep RTU cost data) vs CASCADE (delete RTU rows, recalc) — not fully decided for all paths |
| **Docs** | `docs/architecture/cost-breakdown/` (phased delivery, open concerns) |

---

## Related automated PRs (Glitchtip triager)

| PR | Focus | Overlaps with |
|----|--------|----------------|
| [#6166](https://github.com/project-koku/koku/pull/6166) | COST-7736 — null `rate_id` before Rate delete | Issue #1 |
| [#6159](https://github.com/project-koku/koku/pull/6159) | Null `cost_model_id` before CostModel delete | Issue #2 |
| [#6128](https://github.com/project-koku/koku/pull/6128) | Guard worker when cost model gone before INSERT | Issues #3/#4 |

These are **not interchangeable**. Merging one does not fix the others.

---

## Production scale (RTU row counts)

Snapshot from Martin (prod, 2026-07-07) — **needs Cody / ongoing validation:**

| Bucket (rows) | Tenants |
|---------------|---------|
| 0 | 1,748 |
| 1–99 | 1 |
| 100–999 | 1 |
| 1K–9K | 2 |
| 10K–49K | 18 |
| 50K–99K | 7 |
| 100K–499K | 16 |
| 500K–999K | 2 |
| 1M+ | 3 |
| **Total** | ~1,798 tenants, ~15.6M rows |

Implication: performance fixes (#5) matter mainly for a **small number of large tenants**; correctness fixes (#1–#4) can still hit any tenant with RTU data + cost model edits.

---

## Open questions (for team discussion)

1. Do we fix symptoms path-by-path, or one **shared helper** (e.g. detach RTU before any Rate/CostModel delete)?
2. Should DB FKs be migrated to explicit `ON DELETE SET NULL` / `CASCADE` at PostgreSQL level?
3. Index on `rate_id` (and `cost_model_id`?) — required before any null-before-delete fix ships?
4. How do we handle pipeline races (#3, #4) — guard in worker, retry, or accept NULL FK on INSERT?
5. Is Cost breakdown / RTU **frozen** (stability only) until AI Grid PoC, or minimal fixes allowed?
6. Run diagnostic FK constraint query per tenant schema (see Martin's review) to confirm root cause?

---

## Proposed path forward: smart revert — restore legacy flow, fix RTU properly before re-enabling

### Why fixing in place is risky

The gap analysis (GAP-1 through GAP-8) describes real correctness and performance bugs in the RTU pipeline. The fundamental problem with fixing them in place is that **live production data is actively flowing through the table**. GAP-1 and GAP-3 cause HTTP 500s on cost model edits; GAP-6 and GAP-7 silently accumulate duplicate cost rows; GAP-5 means any null-before-delete fix would trigger a sequential scan across millions of rows inside a synchronous API transaction. Fixing individual symptoms one at a time while real data flows creates a high risk of making things worse before they get better — a cascading series of one-off PRs targeting Glitchtip alerts without addressing the root causes.

### What "smart revert" means

Rather than a full git revert of Phase 2/3, preserve the RTU infrastructure (table, migrations, SQL files) and keep the Unleash flag gate in the code — but ensure the **legacy direct-write path is the only path that runs in production** until the gaps are fixed and the feature is consciously re-enabled.

The revert has two layers:

**1. Phase 3 revert**

Phase 3 had made the monthly/tag/VM SQL unconditionally write to `rates_to_usage` and removed the flag gate. This meant the flag had no effect — RTU ran regardless. Proposed reversal:

- Each SQL file changed in Phase 3 would be preserved as a `*_rtu.sql` variant (the RTU version).
- The original filenames would be restored to their pre-Phase 3 content — these write directly to `reporting_ocpusagelineitem_daily_summary`.
- The Unleash flag gate would be properly restored in `update_summary_cost_model_costs`:
  - **Flag ON** → full RTU path (`insert_usage_rates_to_usage` + `*_rtu.sql` variants + `aggregate_rates_to_daily_summary`)
  - **Flag OFF** → legacy path (all SQL writes directly to daily summary, no aggregate step)
- Since the flag is currently **OFF in production**, the legacy path would run immediately with no further config change.

**2. Phase 2 RTU path (flag ON only)**

The Phase 2 RTU files (`insert_usage_rates_to_usage.sql`, `aggregate_rates_to_daily_summary.sql`, `insert_markup_rates_to_usage.sql`) would remain in place, wired to the flag-ON path only. They would not run until the flag is explicitly turned on. No data would flow through `rates_to_usage` while the flag stays off.

### What the legacy path would look like

| Step | Flag OFF (legacy) | Flag ON (RTU, re-enabled later) |
|------|-------------------|----------------------------------|
| Usage costs | `_update_usage_costs` → `usage_costs.sql` → daily summary | `_update_usage_rates_to_usage` → `insert_usage_rates_to_usage.sql` → RTU |
| Monthly costs | `populate_monthly_cost_sql` → original `monthly_cost_*.sql` → daily summary | same method, `*_rtu.sql` variants → RTU |
| Tag costs | `populate_tag_usage_costs` → original `infrastructure_tag_rates.sql` etc. → daily summary | same method, `*_rtu.sql` variants → RTU |
| VM costs | `populate_vm_usage_costs` → original `hourly_cost_virtual_machine.sql` etc. → daily summary | same method, `*_rtu.sql` variants → RTU |
| Aggregate | not run | `aggregate_rates_to_daily_summary.sql` rebuilds daily summary from RTU |
| Markup | `populate_markup_cost` ORM UPDATE → daily summary | same + `insert_markup_rates_to_usage.sql` → RTU |

### Proposed next steps

| Step | Owner | Output |
|------|--------|--------|
| 1 | Cody | ~~Current state analysis~~ → **[rates-to-usage-gap-analysis.md](./rates-to-usage-gap-analysis.md)** (GAP-1–8) |
| 2 | Team | Review and agree on this path forward |
| 3 | Cody | Phase 3 revert PR: restore original SQL files, add `*_rtu.sql` variants, restore Unleash flag gate |
| 4 | Team | Validate issue list and gap analysis; confirm production behaviour with flag OFF |
| 5 | Team | Fix GAP-5 first (standalone index migration) — makes subsequent FK null-before-delete operations fast |
| 6 | Team | Fix GAP-1 + GAP-3 together (`sync_rate_table` + `PriceListManager` schema context + pre-delete RTU nullification) |
| 7 | Team | Fix GAP-6 + GAP-7 (add scoped DELETE before monthly/tag INSERT into RTU SQL files) |
| 8 | Team | Fix GAP-2, GAP-4, GAP-8 (cost model CASCADE, report_period_id orphan paths, cost_category SET_NULL) |
| 9 | Team | Integration test RTU path end-to-end with real data on stage |
| 10 | Team | Re-enable Unleash flag on stage; validate; roll out to production tenants incrementally |

**Recommendation on open PRs:** do not merge PR #6166, PR #6159, or PR #6128 in isolation. These address individual symptoms but not the root causes. Revisit after the gap fix PRs are in, or supersede them.

---

## References

- **Cody's gap analysis:** [rates-to-usage-gap-analysis.md](./rates-to-usage-gap-analysis.md)
- Jira: [COST-7736](https://redhat.atlassian.net/browse/COST-7736)
- PR: [#6166](https://github.com/project-koku/koku/pull/6166) (paused)
- Deep dive (leads, verify claims): [pr-6166-review.md](https://github.com/project-koku/koku/blob/pr-6166-adversarial-review/pr-6166-review.md)
- Architecture: `docs/architecture/cost-breakdown/` (phased delivery, data model, open concerns)
- RTU model: [`koku/reporting/provider/ocp/models.py`](../../../koku/reporting/provider/ocp/models.py) (`RatesToUsage`)
- Rate sync: [`koku/cost_models/rate_sync.py`](../../../koku/cost_models/rate_sync.py) (`sync_rate_table`)

---

## Changelog

| Date | Author | Change |
|------|--------|--------|
| 2026-07-07 | Victor Sizilio | Initial draft from COST-7736 investigation and team thread |
| 2026-07-07 | Victor Sizilio | Link to Cody's [rates-to-usage-gap-analysis.md](./rates-to-usage-gap-analysis.md); issue ↔ GAP mapping |
| 2026-07-07 | Cody Myers | Add "Proposed path forward: smart revert" section; document Phase 3 revert approach and flag gate restoration; update proposed next steps; mark issues #3/#4 as mitigated by revert |
