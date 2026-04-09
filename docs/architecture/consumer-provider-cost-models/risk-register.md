# Risk Register — COST-3920 Consumer-Provider Cost Models

**Parent**: [README.md](README.md) · **Status**: Design Proposal

---

## Summary

| ID | Risk | Severity | Status |
|----|------|----------|--------|
| R1 | Daily summary table migration on high-volume partitioned table | **Critical** | **Resolved by codebase pattern** — nullable `AddField` + RunSQL backfill |
| R3 | RBAC service has no "context" dimension; cross-service dependency | **High** | **Resolved by precedent** — `IngressAccessPermission` pattern |
| R4 | 3× storage multiplier on cost data (summary + UI tables) | **High** | Resolvable — proposed mitigation below |
| R13 | OCP-on-cloud cost rows appear in OCP summaries — context interaction unclear | Medium | **Resolved by code** — cloud costs already context-independent |
| R20 | On-prem vs SaaS scope not defined — affects RBAC path and migration strategy | **High** | **Resolved by code** — cost models are universal; follow existing pattern |
| R2 | Pipeline runs N× per cluster (3 contexts = 3× compute) | **High** | Resolvable — proposed mitigation below |
| R5 | `CostModelDBAccessor.cost_model` uses `.first()` — single-model assumption | **High** | Resolvable — proposed mitigation below |
| R6 | SQL DELETE→INSERT pattern overwrites context data without discriminator | **High** | Resolvable — proposed mitigation below |
| R7 | Distribution logic is per-provider, not per-context | Medium | Resolvable — proposed mitigation below |
| R8 | Currency annotation joins CostModelMap without context | Medium | Resolvable — proposed mitigation below |
| R9 | `update_provider_uuids` blocks multi-assignment | Medium | Resolvable — proposed mitigation below |
| R10 | Migration ordering collision with predecessor PRs | Medium | **Resolved** — confirmed merge order #5981→#5983→#5984 |
| R11 | 13 UI summary SQL files need context column + GROUP BY | Medium | Resolvable — proposed mitigation below |
| R12 | Audit trigger does not capture context | Medium | Resolvable — proposed mitigation below |
| R14 | `CostModelMap.provider_uuid` is not a Django FK | Low | Resolvable — proposed mitigation below |
| R15 | Max 3 contexts constraint is application-level | Low | Resolvable — proposed mitigation below |
| R16 | Default context cannot be deleted | Low | Resolvable — proposed mitigation below |
| R17 | Empty context (no cost model) must still show metering at $0 | Low | Resolvable — proposed mitigation below |
| R18 | Tag-based CASE statements repeated per context | Low | Resolvable — proposed mitigation below |
| R19 | Celery task dedup collision for same provider across contexts | Medium | Resolvable — proposed mitigation below |
| R21 | Deployment sequencing — code before backfill causes data duplication | **High** | Proposed mitigation: write-freeze flag + deployment runbook |

---

# Part 1 — Risks Informed by Codebase Analysis

Of the original 5 TL-blocked risks, **3 are now fully resolved** by
codebase evidence, **1 is narrowed**, and **1 remains a process
question**. Each section includes the code evidence that informed
our resolution.

---

## R13 (was TQ-2): OCP-on-Cloud Context Interaction — RESOLVED BY CODE

**Severity**: Medium · **Status**: **Resolved** — cloud costs are
already context-independent by design.

### Code evidence

1. **Separate columns**: Cloud infrastructure costs use
   `infrastructure_raw_cost` (+ `infrastructure_markup_cost`). Cost
   model charges use `cost_model_cpu_cost`, `cost_model_memory_cost`,
   etc. These are **different columns** on the same table.

2. **Different rate type markers**: Cloud rows have
   `cost_model_rate_type = NULL`. Cost model rows have explicit
   values (`'Infrastructure'`, `'Supplementary'`, distributed types).

3. **SQL isolation**: Cost model DELETE→INSERT operations scope by
   `cost_model_rate_type = {{rate_type}}` — they **never touch**
   cloud rows (which have NULL rate type). The SQL explicitly filters:
   ```sql
   AND (cost_model_rate_type IS NULL
        OR cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
   ```
   This means cost model SQL reads from cloud/usage rows as input
   but only DELETEs/INSERTs its own output rows.

4. **Provider map separation**: `OCPProviderMap` already distinguishes:
   - `cloud_infrastructure_cost` → `Sum(infrastructure_raw_cost)`
   - `cost_model_infrastructure_cost` → sum of `cost_model_*` where
     `cost_model_rate_type = 'Infrastructure'`

**Resolution**: No TL decision needed. Adding a `context` column to
cost-model rows (those with non-NULL `cost_model_rate_type`) leaves
cloud rows untouched (`context = NULL`). The report API already
merges both column families in aggregates — cloud costs will continue
to appear in every context response, clearly separated as
infrastructure costs. This is Option C from our original analysis,
and it's the existing behavior.

---

## R1 (was TQ-3): Daily Summary Migration — RESOLVED BY CODEBASE PATTERN

**Severity**: Critical → **Downgraded to Low** (follows established
pattern).

### Code evidence

1. **Established pattern**: Migration `0339` added `cost_model_gpu_cost`
   to `reporting_ocpusagelineitem_daily_summary` using a standard
   nullable `AddField`:
   ```python
   migrations.AddField(
       model_name="ocpusagelineitemdailysummary",
       name="cost_model_gpu_cost",
       field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
   )
   ```

2. **No RunSQL pattern exists**: Grep across all reporting migrations
   found **zero** instances of `RunSQL` with `ADD COLUMN` or
   `ADD COLUMN DEFAULT`.

3. **Partitions handled automatically**: PostgreSQL propagates
   `ALTER TABLE` on the parent to all partitions. The codebase relies
   on this — no per-partition DDL loops exist. Documented in
   `.cursor/rules/migrations.mdc`.

4. **Migration `0341`** added `cost_model_gpu_cost` to **all 13 UI
   summary `*_p` tables** using the same `AddField` pattern.

**Proposed resolution**: Follow the established DDL pattern — add
`cost_model_context` as a **nullable** `CharField(max_length=50, null=True)`
to the daily summary and all 13 UI summary tables.

However, unlike `cost_model_gpu_cost` (a purely additive column),
`cost_model_context` will be used as a **discriminator in SQL WHERE
clauses**:
```sql
DELETE FROM ... WHERE cost_model_context = {{cost_model_context}} AND ...
```

Leaving existing cost-model rows as `NULL` would cause the scoped
DELETE to miss them, producing **duplicate rows** (NULL legacy +
new `'default'` rows) on the first pipeline run after deployment.

**Therefore a RunSQL backfill migration is proposed**:
```sql
UPDATE reporting_ocpusagelineitem_daily_summary
   SET cost_model_context = 'default'
 WHERE cost_model_rate_type IS NOT NULL
   AND cost_model_context IS NULL;
```

The same pattern applies to all 13 UI summary tables. The `WHERE
cost_model_rate_type IS NOT NULL` clause targets only cost-model-
injected rows — cloud/usage rows (with NULL rate type) remain NULL.

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | Nullable AddField + RunSQL backfill | Follows koku DDL precedent; prevents duplicates | Backfill may take time on large tenants | **Proposed** |
| B | Nullable AddField, NULL = default (no backfill) | Simpler | Scoped DELETE misses NULL rows; data duplication | Rejected |
| C | AddField with DEFAULT clause | No separate backfill needed | Not used anywhere in koku; PostgreSQL may rewrite table | Rejected |

See also [R21](#r21-deployment-sequencing) for the write-freeze guard
that prevents race conditions during backfill.

---

## R3 (was TQ-5): RBAC Context Authorization — RESOLVED BY PRECEDENT

**Severity**: High · **Status**: **Resolved** — `IngressAccessPermission`
is direct precedent for Koku-side auth.

### Code evidence

1. **`IngressAccessPermission`** subclasses `SettingsAccessPermission`
   (the RBAC-based class) but adds a Koku-side override:
   ```python
   class IngressAccessPermission(SettingsAccessPermission):
       def has_permission(self, request, view):
           if is_ingress_rbac_grace_period_enabled(customer.schema_name):
               return True  # bypass RBAC entirely
           return super().has_permission(request, view)
   ```

2. **Unleash/schema-scoped feature flag**: The bypass uses
   `UNLEASH_CLIENT.is_enabled(flag, {"schema": schema})` — a
   Koku-managed, per-tenant gate that does not go through the
   RBAC service.

3. **Pattern for COST-3920**: Create a `CostModelContextPermission`
   that subclasses `CostModelsAccessPermission`, adds a Koku-side
   context check (DB-backed, not Unleash), and falls through to
   RBAC for cost model access. When platform RBAC adds
   `cost_model_context`, swap the Koku-side check for the RBAC
   lookup without changing the API.

4. **`RESOURCE_TYPES` in `rbac.py`** already includes `settings`
   with `read`/`write` — adding `cost_model_context` later would
   follow the same pattern.

**Resolution**: Hybrid approach (Option C) is the correct path, and
it follows established codebase conventions. No TL decision needed
on the pattern — only on timing of platform RBAC migration (which
can be deferred).

---

## R20 (was TQ-1): Environment Scope — RESOLVED BY CODE

**Severity**: High → **Low** (follows established pattern).

### Code evidence

1. **Cost model endpoints are universal**: `cost-models/` CRUD and
   `resource-types/cost-models/` are registered **unconditionally**
   in `koku/urls.py` — no `settings.ONPREM` check.

2. **ONPREM gating is rare**: Only 3 routes are ONPREM-gated
   (`source_types`, `application_types`, `applications`). Cost-model-
   related paths are not among them.

3. **`source_type` supports all providers**: `CostModel.source_type`
   uses the full `Provider.PROVIDER_CHOICES` (OCP, AWS, Azure, GCP).
   Cost models are not OCP-only or on-prem-only at the model level.

4. **D6 pattern from COST-573**: Backend logic is environment-agnostic.
   `ONPREM` only gates URL registration. COST-3920 should follow the
   same pattern.

**Proposed resolution**: Ship context APIs universally, matching the
existing cost model pattern. Gating behind `ONPREM` would break the
established convention.

For migration data consistency, we propose a **dedicated Unleash flag**
`cost-management.backend.disable-cost-model-context-writes` following
the pattern established by PR #5983 (`COST_MODEL_WRITE_FREEZE_FLAG =
"cost-management.backend.disable-cost-model-writes"`). This flag:

- **Blocks** context creation/update via a serializer guard
  (`_check_context_write_freeze()` on `CostModelContextSerializer`)
- **Blocks** context-tagged pipeline writes via a task guard in
  `update_cost_model_costs` (skips when flag active + context is set)
- **Allows** all reads (GET/list on contexts and reports)
- Uses `is_context_writes_disabled(schema)` helper in
  `masu/processor/__init__.py`

**On-prem consideration**: `MockUnleashClient` returns `False` for all
flags, making the write-freeze a no-op. On-prem deployments follow
migrations-first deployment, which already prevents the race condition.

See [phased-delivery.md § Deployment Runbook](./phased-delivery.md#deployment-runbook)
for the full deployment sequence.

---

## R10 (was TQ-4): Predecessor PR Sequencing — RESOLVED

**Severity**: Medium → **Low** (confirmed merge order).

In-flight PRs modify the same cost model infrastructure:
- PR #5981 (COST-575 Price List API) — accessor, updater, manager
- PR #5983 (COST-7249 Rate dual-write) — models, migrations, manager
- PR #5984 (COST-7249 Rate backfill) — data migration

**Confirmed merge order**: #5981 → #5983 → #5984. This is the
dependency chain: #5981 establishes the Price List API, #5983 adds
the Rate model + dual-write on top, and #5984 backfills existing
data.

**Resolution**: Continue design now. Begin COST-3920 implementation
after #5984 merges (last in the chain). Run `makemigrations` against
clean main post-merge to get correct migration numbers. The final
state after all 3 PRs land gives us `Rate`, `PriceList`, and the
updated `CostModelManager` — all of which COST-3920 builds on top of.

---

# Part 2 — Resolvable Risks (Proposed Mitigations)

These 15 risks have clear resolutions we can proceed with. Each
includes available options and our proposed approach.

---

## R2: Pipeline Runs N× Per Cluster

**Severity**: High · **Category**: Performance

With 3 contexts, the cost pipeline must execute 3× per provider.

### Available resolutions

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Sequential loop** | Inner loop over contexts inside existing pipeline task | Simple; reuses existing task structure | Total wall-clock = N × single run |
| **B — Parallel Celery tasks** | Dispatch one Celery task per (provider, context) pair | Parallelized; scales with workers | More Celery tasks; cache key changes needed (R19) |
| **C — Single-pass multi-context SQL** | SQL uses UNION ALL or CASE to compute all contexts in one query | Fewest DB round-trips | Complex SQL; harder to debug; couples contexts |

**Proposed**: **Option B**. Per-context tasks are independent and can
run in parallel. The pipeline already dispatches per-provider — adding
a context dimension is incremental. Most tenants will have 1-2
contexts, keeping the common case fast.

---

## R5: `CostModelDBAccessor` Single-Model Assumption

**Severity**: High · **Category**: Code

The accessor uses `.first()` which returns one arbitrary cost model.

### Available resolutions

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Add `context` parameter** | `CostModelDBAccessor(schema, provider_uuid, context=None)` filters by context FK on CostModelMap | Clean; backward-compatible (None = current behavior) | All callers must be updated |
| **B — Return all cost models, let caller pick** | `cost_models` property returns list; caller iterates | Flexible | Pushes complexity to callers; error-prone |

**Proposed**: **Option A**. Add optional `context` parameter. When
`None`, falls back to `.first()` (backward-compatible). When set,
filters by `costmodelmap__context`. 4 files need updating.

---

## R6: SQL DELETE→INSERT Overwrites Without Context Discriminator

**Severity**: High · **Category**: Data integrity

Running the pipeline for context B would delete context A's cost rows.

### Code evidence (from R13 analysis)

The existing SQL already scopes DELETEs by `cost_model_rate_type`:
```sql
DELETE FROM ... WHERE cost_model_rate_type = {{rate_type}} AND monthly_cost_type IS NULL
```
Cloud rows (`cost_model_rate_type = NULL`) are untouched. The
`context` column follows the same pattern — add it to the WHERE
clause alongside `rate_type`.

### Available resolutions

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Add `context` to all SQL WHERE clauses** | `AND context = {{context}}` in DELETE and source-filtering clauses | Clean; explicit; correct; follows existing `rate_type` scoping pattern | 29+ SQL files to modify (plus self-hosted) |
| **B — Use `cost_model_rate_type` to encode context** | Prefix rate type: `Infrastructure:Provider` | No new column needed | Breaks existing semantics; fragile; ugly |

**Proposed**: **Option A**. Mechanical change across ~37 SQL files.
Repetitive but straightforward. The pattern is identical to existing
`cost_model_rate_type` scoping — add `AND context = {{context}}`
next to every `AND cost_model_rate_type = {{rate_type}}`. Create a
PR checklist to ensure no file is missed.

---

## R7: Distribution Logic Per-Provider, Not Per-Context

**Severity**: Medium · **Category**: Correctness

Different contexts may use different distribution strategies (CPU vs
memory). Distribution SQL must be scoped by context.

**Proposed**: Pass `context` parameter to
`populate_distributed_cost_sql`. The distribution SQL already scopes
by `source_uuid` — adding `context` is the same pattern. Each
context's cost model provides its own `distribution_info`, which the
updater already reads per cost model.

---

## R8: Currency Annotation Joins Without Context

**Severity**: Medium · **Category**: API correctness

Report query handler builds a `source_to_currency_map` joining
`CostModel → CostModelMap`. Multiple contexts = multiple currencies.

**Proposed**: Filter the currency join by the request's
`cost_model_context` parameter. Falls out naturally from the API
parameter threading (GA-6 in gap analysis). When no context is
specified, use the default context's currency.

---

## R9: `update_provider_uuids` Blocks Multi-Assignment

**Severity**: Medium · **Category**: Code

Manager rejects any provider that already has a `CostModelMap` row.

### Available resolutions

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Check per-context uniqueness** | `filter(provider_uuid=uuid, context=context)` | Correct; minimal change | Must ship atomically with context column migration |
| **B — Drop the check entirely** | Let DB unique constraint enforce | Simpler code | Loses descriptive error message; relies on DB IntegrityError |

**Proposed**: **Option A**. Change the filter to include `context`.
The descriptive error message is valuable for API consumers. Ship
as a single migration + code change to avoid intermediate breakage.

---

## R10: Migration Ordering Collision — RESOLVED

**Severity**: Medium → Low · **Category**: Process

Confirmed merge order: **#5981 → #5983 → #5984**. Design proceeds
now; implementation starts after #5984 lands. Run `makemigrations`
against clean main post-merge to get correct migration numbers.

---

## R11: 13 UI Summary SQL Files Need Context

**Severity**: Medium · **Category**: Effort

All UI summary SQL files follow the same DELETE→INSERT pattern.

**Proposed**: Apply the pattern mechanically:
1. Add `context` to DELETE WHERE clause
2. Add `context` to INSERT column list
3. Add `context` to GROUP BY

Create a checklist of all 13 files. Add a test that asserts every
`reporting_ocp_*_summary_p` table has the `context` column. Verify
in code review using `rg 'context' sql/openshift/ui_summary/`.

---

## R12: Audit Trigger Does Not Capture Context

**Severity**: Medium · **Category**: Auditability

**Proposed**: Update the `process_cost_model_audit()` trigger to
include a `contexts` array in the audit row, aggregated from
`cost_model_map` alongside the existing `provider_uuids` array.
Straightforward DDL change in a new migration.

---

## R14: `CostModelMap.provider_uuid` Not a Django FK

**Severity**: Low · **Category**: Pre-existing

`provider_uuid` is stored by value, not as a Django `ForeignKey` to
`Provider`. This means no cascade cleanup when a provider is deleted.

**Proposed**: Accept as-is. This is a pre-existing design choice.
Adding context does not change the risk profile. Provider deletion
already has application-level cleanup in the manager. If context
cleanup is needed on provider delete, add it to the same code path.

---

## R15: Max 3 Contexts — No DB Enforcement

**Severity**: Low · **Category**: Data integrity

The PRD limits contexts to 3 per tenant, but without DB enforcement
the application could create more.

### Available resolutions

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Serializer validation only** | Check `CostModelContext.objects.count() < 3` before create | Simple | Bypassable via shell or direct DB |
| **B — DB trigger** | Postgres trigger rejects INSERT if count ≥ 3 | Bulletproof | More complex; harder to test |
| **C — Serializer + DB CHECK** | Serializer validates; DB CHECK on a `position` column (1, 2, 3) | Belt and suspenders | Slightly more complex model |

**Proposed**: **Option C**. Add a `position` field (1, 2, or 3)
with a DB CHECK constraint. The serializer enforces max 3 and
assigns the next available position. This is simple and robust.

---

## R16: Default Context Cannot Be Deleted

**Severity**: Low · **Category**: Business rule

**Proposed**: Guard in `CostModelContextSerializer.validate_delete()`
and `CostModelContextManager.delete()`: if `is_default=True`, raise
`ValidationError("The default context cannot be deleted")`. Add a
partial unique index `CREATE UNIQUE INDEX ... ON cost_model_context
(is_default) WHERE is_default = TRUE` to enforce one default at the
DB level.

---

## R17: Empty Context Shows Metering at $0

**Severity**: Low · **Category**: Existing behavior

A context with no cost model assigned should show usage but $0 cost.

**Proposed**: Already works. When `CostModelDBAccessor` finds no cost
model for a (provider, context), it returns empty rates. The pipeline
still runs for OCP providers (distribution and UI summary refresh).
Usage data comes from ingestion, which is context-independent.
Verify with a test that covers the "no cost model for context" path.

---

## R18: Tag-Based CASE Statements Repeated Per Context

**Severity**: Low · **Category**: Performance

The Python-built CASE statements for tag-based monthly costs run
per context with different rates.

**Proposed**: Accept. The CASE statements are built dynamically from
the cost model's tag rates. Each context has its own cost model with
its own rates, so the statements are naturally different. No
optimization needed — the pattern is the same, just executed N times.

---

## R19: Celery Task Dedup Collision

**Severity**: Medium · **Category**: Concurrency

`update_cost_model_costs` uses `worker_cache` with key
`(schema, provider_uuid)`. Multiple per-context tasks would collide.

**Proposed**: Include `context` in the cache key:
`(schema, provider_uuid, context_id)`. One-line change in
`tasks.py` where the cache key is composed.

---

## R21: Deployment Sequencing

**Severity**: High · **Category**: Data integrity

If new application code (with context-aware pipeline) deploys before
the backfill migration runs, the pipeline will write context-tagged
rows (`cost_model_context = 'default'`) alongside existing NULL rows
that were not yet backfilled. This causes data duplication on report
queries.

### Proposed mitigation

1. **Write-freeze Unleash flag** (`cost-management.backend.disable-cost-model-context-writes`) — enable before migration, disable after code deployment
2. **Deployment runbook** enforcing: Enable flag → Run migrations → Deploy code → Disable flag
3. **On-prem**: MockUnleashClient makes freeze a no-op; migrations-first deployment already prevents the race

See [phased-delivery.md § Deployment Runbook](./phased-delivery.md#deployment-runbook).

---

## Tech Lead Questions — All Resolved

All 5 original TL-blocked questions have been resolved through
codebase analysis and confirmed inputs. No TL decisions are blocking
design or implementation.

| # | Question | Risk | Resolution |
|---|----------|------|------------|
| ~~TQ-1~~ | Environment scope | R20 | **Resolved by code** — cost models are universal today; context APIs follow the same pattern |
| ~~TQ-2~~ | Cloud-backed infra costs | R13 | **Resolved by code** — cloud rows use separate columns + NULL rate type; already context-independent |
| ~~TQ-3~~ | Daily summary migration | R1 | **Resolved by codebase pattern** — nullable `AddField` (0339, 0341 precedent); NULL = default context |
| ~~TQ-4~~ | PR sequencing | R10 | **Resolved** — confirmed merge order #5981 → #5983 → #5984 |
| ~~TQ-5~~ | RBAC strategy | R3 | **Resolved by precedent** — `IngressAccessPermission` hybrid pattern |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-08 | Initial risk register: 20 risks, 5 TL questions |
| v1.1 | 2026-04-08 | Restructured: TL-blocked risks with options/trade-offs; resolvable risks with proposed mitigations |
| v2.0 | 2026-04-08 | Codebase analysis: resolved TQ-2, TQ-3, TQ-5 from source code; narrowed TQ-1; only TQ-4 remains fully open |
| v2.1 | 2026-04-08 | TQ-4 resolved: confirmed merge order #5981→#5983→#5984 |
| v2.2 | 2026-04-08 | R20 resolved: universal scope follows established cost model pattern; all 5 TL questions now resolved |
| v3.0 | 2026-04-09 | Design proposal: R1 corrected (backfill required, not optional); R20 updated with dedicated write-freeze Unleash flag per PR #5983 pattern; R21 added (deployment sequencing risk + write-freeze mitigation) |
