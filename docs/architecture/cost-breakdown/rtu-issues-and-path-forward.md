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
| **Status** | **Not fixed by PR #6166**; related to bot PR #6128 |
| **Notes** | Different direction than #1 (INSERT vs DELETE) |

### 4. Pipeline INSERT with stale `cost_model_id` (race)

| | |
|---|---|
| **Symptom** | Same as #3 but on `cost_model_id` |
| **Evidence** | Glitchtip **STAGE-5HI** (9 events, stage) |
| **Status** | Open; same family as #3 |

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

## Proposed next steps (draft)

| Step | Owner | Output |
|------|--------|--------|
| 1 | Cody | ~~Current state analysis~~ → **[rates-to-usage-gap-analysis.md](./rates-to-usage-gap-analysis.md)** (GAP-1–7) |
| 2 | Team | Validate / correct this issue list and Cody's gaps; resolve conflicts (e.g. GAP-2 CASCADE vs null-before-delete) |
| 3 | Team | Decide: tactical patches vs cohesive design reset |
| 4 | TBD | Jira tickets per issue cluster (not per bot PR unless agreed) |
| 5 | TBD | Root cause investigation (DB constraints on partitioned RTU) |

**Explicitly paused until plan agreed:** merge PR #6166 and similar tactical fixes.

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
