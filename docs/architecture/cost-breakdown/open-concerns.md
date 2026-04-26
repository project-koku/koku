# Concerns Register — Cost Breakdown Design Review

This document captures concerns identified during a critical review of the
cost breakdown technical design ([COST-7249](https://redhat.atlassian.net/browse/COST-7249)).
Each concern is grounded in code evidence, not supposition.

All five concerns are now resolved. Concerns 1, 2, 3, and 4 were
self-resolved by folding fixes directly into the design specs.
Concern 5 was resolved by the tech lead (Option 1 is non-negotiable;
remove Option 2 fallback language). Concern 3's six implementation
gaps (A-F) have been closed with conservative defaults documented in
[api-and-frontend.md](./api-and-frontend.md).

---

## Design Strengths

Before diving into concerns, the design has several notable strengths
worth acknowledging:

- **Grounded in source code triage.** All 4 open questions (OQ-1 through
  OQ-4) and 9 implementation questions (IQ-1 through IQ-9) were resolved
  by reading koku source, not by assumption.
- **Reuses COST-575 infrastructure.** Phase 1 builds on the existing
  `price_list` table and `PriceListCostModelMap` junction table rather
  than creating parallel tables.
- **Every phase has a realistic rollback.** Phases 1-4 can be reverted
  with code changes + data cleanup. Phase 5's rollback honestly requires
  a backup.
- **Risk register with concrete decision rationales.** 20 risks (R1-R20)
  with alternatives-evaluated tables, benchmarks with acceptance criteria,
  and a phase matrix.

---

## Self-Resolved Concerns (Concern 3 and Gaps A-F)

### Concern 3: `_sync_rate_table()` Delete-All Pattern and `RatesToUsage.rate_id` FK — RESOLVED

**Status**: Self-resolved. All 6 implementation gaps (A-F) closed with
conservative defaults documented in
[api-and-frontend.md](./api-and-frontend.md#diff-based-sync-design-decisions).
No tech lead escalation required — decisions use safe defaults that can
be refined later without rework.

#### Tech Lead Response Summary

The tech lead proposed:
1. Replace delete-all + recreate with **diff-based sync** (update
   existing rates by `rate_id`, create new rates, delete only removed
   rates) — preserves `Rate.uuid` for unchanged rates.
2. Include `rate_id` in **API payloads** so the frontend can round-trip
   stable Rate UUIDs.
3. Change `RatesToUsage.rate` FK from **`SET_NULL` to `CASCADE`**.
4. **Scoped recalculation** — only recalculate the changed rate's costs.

#### Blast Radius Re-Triage

##### Critical finding: `rate_id` is never populated in the SQL pipeline

The PoC SQL `insert_usage_rates_to_usage.sql` INSERT column list omits
`rate_id` entirely. The `custom_name` column serves as the denormalized
per-rate identifier. This means:

- Under the current design, `RatesToUsage.rate_id = NULL` for **all** rows
- `CASCADE` vs `SET_NULL` on the `rate` FK is **moot** — NULL FKs don't cascade
- The FK constraint is decorative until the SQL pipeline populates it

**Why this gap exists**: Under the original delete-all + recreate
pattern, `Rate.uuid` values were **ephemeral** — every cost model API
update deleted all Rate rows and created new ones with new UUIDs.
Populating `rate_id` in `RatesToUsage` would have been pointless because
the referenced UUIDs would go stale on the next update. The `custom_name`
denormalization was the intentional per-rate identifier. The `rate` FK
on the model was future-proofing, not a functional dependency.

The tech lead's diff-based sync changes this: `Rate.uuid` values are now
**stable** across updates (unchanged rates keep their UUID). This makes
`rate_id` in `RatesToUsage` a durable, meaningful link — but the SQL
pipeline hasn't been updated to reflect this architectural pivot.

**Adopted mitigation**: Populate `rate_id` starting in **Phase 2**,
when the first SQL INSERT into `rates_to_usage` ships. The Python
orchestration already knows which rate it's processing — it passes
`custom_name` as a SQL parameter and can pass `Rate.uuid` alongside
it. Each SQL file adds one column to its INSERT list. Phase 3's 25
files follow the same pattern. This unlocks CASCADE, scoped
recalculation, and any future JOIN from `RatesToUsage` back to `Rate`.

For `CASCADE` to have real effect, **every SQL INSERT into
`rates_to_usage` must populate `rate_id`** — this is now scoped for
Phase 2 onward. `SET_NULL` stays on the FK until `rate_id` is
populated; CASCADE switch deferred until Phase 2 benchmarks confirm
performance on large partitions.

##### Layer 1: Diff-based `_sync_rate_table()` (Phase 1)

| What changes | Where | Impact |
|---|---|---|
| `_sync_rate_table()` rewrite | `cost_model_manager.py` | Match by `rate_id` (if present) or `custom_name`, update/create/delete individually |
| `RateSerializer` adds `rate_id` | `serializers.py` | Optional UUID, read-write. GET includes it; PUT may include it. |
| Frontend `RateRequest` adds `rate_id` | `koku-ui` `api/rates.ts` | Coordinated frontend change. Backward-compatible: omitting degrades to match-by-`custom_name`. |
| API contract documented | `api-and-frontend.md` | New field in rate objects |
| Phase 1 validation expanded | `phased-delivery.md` | Test: update cost model → unchanged rates keep their UUID |

**Backward compatibility**: If the frontend doesn't send `rate_id`, the
backend diffs by `custom_name` (using the existing `unique_together`
constraint). Rename = delete + create rather than update. Full
diff-based sync activates once the frontend ships `rate_id` support.

##### Layer 2: `rate_id` in SQL pipeline (currently unscoped)

For the `rate` FK to be meaningful, every SQL INSERT into `rates_to_usage`
must populate `rate_id`. This requires either:
- Passing `rate_id` as a SQL parameter (Python looks up `Rate.uuid` by
  `(price_list_id, custom_name)` before running SQL), or
- Adding a JOIN to `cost_model_rate` in the SQL itself

**Scope impact**: 1 PoC SQL + 1 Phase 2 SQL + 25 Phase 3 SQL files +
5 Phase 4 distribution SQL files + 6 accessor methods = **38 file
modifications** not currently scoped in any phase.

Markup rows: `rate_id = NULL` (correct — markup has no Rate row).

##### Layer 3: `SET_NULL` → `CASCADE` (only meaningful after Layer 2)

| Change | Impact |
|---|---|
| Django model FK and M3 DDL | `on_delete=CASCADE` |
| Rate deleted via diff-based sync | CASCADE deletes all `RatesToUsage` rows for that rate **across ALL monthly partitions** |
| Current-month recalculation | Recreates current month's data correctly |
| **Historical months** | Lose `RatesToUsage` data for deleted rate permanently |

**Why CASCADE is safe**: `RatesToUsage` is intermediate computation
data, not source-of-truth. The daily summary and `OCPCostUIBreakDownP`
have already materialized the values. A future historical recalculation
would correctly exclude the deleted rate. No existing SQL JOINs
`rates_to_usage` to `cost_model_rate` (confirmed by full search of all
design docs, PoC SQL, and `sql-pipeline.md`).

**Performance concern**: For large tenants, a single Rate deletion
could CASCADE-delete millions of rows across partitions. Should be
benchmarked as part of Phase 2.

##### Layer 4: Scoped recalculation (deferred optimization)

Requires `rate_id` populated in `RatesToUsage` (Layer 2) to know which
rows to recalculate. Non-trivial SQL and Celery changes. Not a Phase 1
requirement — current full-window recalculation is correct, just less
efficient.

##### Confirmed safe (no blast radius)

| Area | Why safe |
|---|---|
| Aggregation SQL | Uses `custom_name`, not `rate_id` |
| Breakdown table population | Reads `RatesToUsage` directly, no FK to `Rate` |
| Daily summary | No FK to `Rate`; aggregation is one-way SUM |
| Markup rows (`rate=None`) | CASCADE doesn't touch NULL FKs |
| Partition cleanup (`purge_expired_report_data_by_date`) | Drops whole partitions, not individual rows |
| `cost_model` FK on `RatesToUsage` | Already populated by SQL; same pattern, not raised by tech lead |

##### Missing from current design (gap)

| Gap | Impact |
|---|---|
| `rate_id` column not in PoC SQL INSERT | FK is decorative; CASCADE has no effect |
| No index on `rates_to_usage(rate_id)` | CASCADE performance on millions of rows; needed for future scoped recalculation |
| 38 SQL files need `rate_id` parameter | Significant Phase 2/3 scope expansion |
| `cost_model` FK also `SET_NULL` | Same CASCADE reasoning applies; already populated in SQL unlike `rate_id` |

#### Due Diligence Findings

The following gaps were identified by verifying the tech lead's proposal
claim by claim against the actual koku codebase (`serializers.py`,
`cost_model_manager.py`, `ocp_cost_model_cost_updater.py`, `tasks.py`).

##### Gap A: GET responses won't include `rate_id` without explicit work — CLOSED

**Finding**: `RateSerializer.to_representation()` builds a fixed output
dict and does not pass through arbitrary extra keys from the JSON blob.

**Resolution**: `rate_id` declared as explicit `UUIDField(required=False,
allow_null=True)` on `RateSerializer`. `to_representation()` updated to
emit `rate_id` when present. `_sync_rate_table()` injects `Rate.uuid`
into the JSON blob during dual-write. See
[api-and-frontend.md](./api-and-frontend.md#rateserializer--add-custom_name-and-rate_id-fields).

##### Gap B: Backward-compatible path + CASCADE = historical data loss — CLOSED

**Finding**: If clients don't send `rate_id` and all existing rates are
treated as deleted, CASCADE would destroy all historical `RatesToUsage`
data (not automatically rebuilt for months before current).

**Resolution**: The `_sync_rate_table()` pseudocode matches by
`custom_name` when `rate_id` is absent, preserving `Rate.uuid` for
unchanged rates. CASCADE only fires for genuinely removed rates. No
deployment ordering dependency on the frontend. See
[api-and-frontend.md](./api-and-frontend.md#diff-based-sync-design-decisions).

##### Gap C: Scoped recalculation is significantly harder than described — CLOSED

**Finding**: The `update_summary_cost_model_costs()` pipeline is
monolithic — scoped per-rate filtering requires Celery task signature
changes, dedup key modifications, and per-method branching. The
aggregation step must still process all rates regardless.

**Resolution**: Scoped recalculation is documented as a deferred
optimization (not Phase 1 or 2 scope). Phase 1 uses full-window
recalculation, which is correct but less efficient. See
[api-and-frontend.md](./api-and-frontend.md#scoped-recalculation--deferred-optimization).

##### Gap D: `rate_id` security validation — CLOSED

**Finding**: Existence check alone is insufficient — a user could send
a `rate_id` from a different cost model within the same schema.

**Resolution**: The `_sync_rate_table()` pseudocode validates `rate_id`
against the existing rates dict (keyed by UUID), which is scoped to the
current `price_list`. Invalid or foreign `rate_id` values raise
`CostModelException`. See
[api-and-frontend.md](./api-and-frontend.md) § `_sync_rate_table()`.

##### Gap E: Unique constraint ordering in diff operations — CLOSED

**Finding**: Rename + create-with-old-name in the same PUT causes
transient `UniqueConstraint` violations if operations aren't ordered.

**Resolution**: The `_sync_rate_table()` pseudocode enforces
**delete → update → create** ordering within the transaction. See
[api-and-frontend.md](./api-and-frontend.md) § `_sync_rate_table()`.

##### Gap F: Change detection needs field classification — CLOSED

**Finding**: Without field classification, every metadata edit (e.g.
`description` typo fix) triggers unnecessary full recalculation.

**Resolution**: `COST_AFFECTING_FIELDS = {default_rate, tag_values,
metric, cost_type}` is defined in the `_sync_rate_table()` pseudocode.
`description` and `custom_name` are metadata-only — they update the
Rate row but do not trigger Celery recalculation. Stale `custom_name`
on existing `RatesToUsage` rows is acceptable (refreshed on next full
recalculation cycle). See
[api-and-frontend.md](./api-and-frontend.md#diff-based-sync-design-decisions).

#### Resolution Summary — Gaps A-F

All gaps have been closed with conservative defaults. The full
pseudocode is in [api-and-frontend.md](./api-and-frontend.md).

| Gap | Resolution | Where documented |
|-----|-----------|------------------|
| **A**: GET won't emit `rate_id` | `rate_id` declared as explicit `UUIDField` on `RateSerializer`. `to_representation()` updated to include it. `rate_id` injected into JSON blob during `_sync_rate_table()` dual-write. | `api-and-frontend.md` § RateSerializer |
| **B**: Backward-compat + CASCADE = data loss | Backend matches by `custom_name` when `rate_id` is absent (preserves UUIDs). CASCADE only fires for genuinely removed rates. No deployment ordering dependency on frontend. | `api-and-frontend.md` § Diff-based sync |
| **C**: Scoped recalculation harder than described | Deferred as a future optimization. Phase 1 uses full-window recalculation (current month). Monolithic pipeline is correct, just less efficient. | `api-and-frontend.md` § Scoped recalculation |
| **D**: `rate_id` security validation | Validated for ownership — `rate_id` must belong to the correct `price_list` for this cost model, not just exist. | `api-and-frontend.md` § `_sync_rate_table()` pseudocode |
| **E**: Unique constraint ordering | Diff operations ordered: deletes → updates → creates. Avoids transient `UniqueConstraint` violations without `DEFERRABLE` constraints. | `api-and-frontend.md` § `_sync_rate_table()` pseudocode |
| **F**: Change detection classification | `COST_AFFECTING_FIELDS = {default_rate, tag_values, metric, cost_type}` triggers recalculation. `description` and `custom_name` are metadata-only (no recalc). Conservative Phase 1 approach. | `api-and-frontend.md` § Diff-based sync |

**`rate_id` in SQL pipeline**: Scoped for Phase 2 onward. Each SQL
INSERT into `rates_to_usage` adds `rate_id` as a parameter (Python
looks up `Rate.uuid` before running SQL). `SET_NULL` stays on the FK
until `rate_id` is populated; CASCADE switch deferred until Phase 2
benchmarks confirm performance on large partitions.

## Tech Lead Resolved Concern

### Concern 5: No Defined Fallback Trigger from IQ-9 Option 1 to Option 2 — RESOLVED

**Status**: Resolved by tech lead decision

#### Tech lead decision

The tech lead confirmed that back-allocation (Option 2) should **not**
be kept as a runtime fallback. The target architecture is Option 1
end-to-end (distribution maintains per-rate identity) and issues in that
path should be fixed directly rather than switching approaches.

#### Due diligence note

This decision is directionally sound, but the current design still needs
Concern 3 Layer 2 implementation (`rate_id` populated in SQL writes to
`rates_to_usage`) before "rate_id flows through naturally" is true in
practice. Until then, Option 1 remains the selected architecture, but
its FK continuity is only partially realized.

#### Actions taken

- Remove Option 2 fallback language from active design guidance in
  `README.md`.
- Keep stronger R18 integration-test assertions (10 checks) as the
  primary correctness safety net for Option 1.
- Concern 3 subsequently self-resolved — all gaps (A-F) closed with
  conservative defaults in `api-and-frontend.md`.

---

## Self-Resolved Concerns (Concerns 1, 2, 4)

The following concerns were identified during the critical review and
have been addressed by updating the design specifications directly.
They are retained here for audit trail.

### Concern 1: Distribution SQL Tests Verify Orchestration, Not Correctness — RESOLVED

**What we found**: Distribution tests in `test_ocp_report_db_accessor.py`
mock `_execute_raw_sql_query` and assert `mock_sql_execute.assert_called()`.
No test runs actual SQL or checks `distributed_cost` values. The
distribution SQL files contain commented-out validation SQL
(`distribute_platform_cost.sql`, lines 163-176) that is never executed.

**What we did**: Added distribution integration tests as a Phase 4
artifact in [phased-delivery.md](./phased-delivery.md#concern-1-resolution--distribution-integration-tests).
Updated R18's mitigation in [risk-register.md](./risk-register.md) to
reflect the stronger test plan. Tests will execute actual SQL against
schema-scoped test databases and assert per-rate proportional
correctness, sum consistency, and edge cases.

### Concern 2: No Observability Instrumentation — RESOLVED

**What we found**: `ocp_cost_model_cost_updater.py` has zero timing
instrumentation. The only related Prometheus metric is
`charge_update_attempts_count` (attempt counter). Koku has Prometheus
infrastructure (`WORKER_REGISTRY`, probe server, Grafana dashboards)
but doesn't instrument the cost model pipeline.

**What we did**: Added Prometheus histograms and gauge as a Phase 2
artifact in [phased-delivery.md](./phased-delivery.md#concern-2-resolution--observability-instrumentation).
Metrics: `cost_model_rtu_insert_duration_seconds`,
`cost_model_aggregation_duration_seconds`, `cost_model_rtu_row_count`,
`cost_model_update_total_duration_seconds`. Thresholds mirror Phase 2
benchmark acceptance criteria.

### Concern 4: On-Prem M2 Migration Without Write Protection — RESOLVED

**What we found**: `MockUnleashClient.is_enabled()` returns `False` by
default (no `fallback_function`). COST-575's migration `0011` used
`select_for_update()` per row. Our M2 pseudocode lacked row-level
locking.

**What we did**: Updated M2 pseudocode in
[data-model.md](./data-model.md#m2-data-migration--pricelist-json-to-rate-rows)
to use `transaction.atomic()` + `select_for_update()` per mapping,
matching 0011's pattern. This provides defense-in-depth for on-prem
(row-level locking) while SaaS uses the Unleash flag (API-level
blocking). Both mechanisms are independent and complementary.

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-02 | Initial: 5 open concerns from critical review. |
| v1.1 | 2026-04-02 | Triage: concerns 1, 2, 4 self-resolved (folded into design specs). Concerns 3, 5 retained for tech lead review with specific questions. |
| v1.2 | 2026-04-03 | Concern 3: blast radius re-triage after tech lead response. Key finding: `rate_id` never populated in SQL pipeline — CASCADE is moot until Layer 2 is scoped. Added 4 decision points. Concern 1 tests strengthened: 10 assertions (up from 4), including Option 2's formula as cross-check (#5). |
| v1.3 | 2026-04-03 | Concern 3: due diligence findings from verifying tech lead's proposal against codebase. Added Gaps A-F: GET serializer won't emit `rate_id` without explicit changes (Gap A), backward-compat + CASCADE = historical data loss (Gap B), scoped recalc harder than described (Gap C), `rate_id` needs price_list ownership validation (Gap D), diff operations need delete→update→create ordering for unique constraint (Gap E), change detection field classification needed (Gap F). Expanded decision points from 3 to 6. |
| v1.4 | 2026-04-03 | Concern 5 marked RESOLVED per tech lead decision: Option 1 is non-negotiable, remove Option 2 fallback language. Clarify Gap B wording ("not automatically rebuilt" instead of "permanently lost") and soften Gap C implementation estimate ("multiple call sites" instead of fixed count). |
| v2.0 | 2026-04-03 | All concerns resolved. Concern 3 Gaps A-F closed with conservative defaults: diff-based `_sync_rate_table()` with `custom_name` fallback (B), `rate_id` on `RateSerializer` + `to_representation()` (A), ownership validation (D), delete→update→create ordering (E), `COST_AFFECTING_FIELDS` classification (F), scoped recalc deferred (C). Pseudocode added to `api-and-frontend.md`. No open concerns remain. |
