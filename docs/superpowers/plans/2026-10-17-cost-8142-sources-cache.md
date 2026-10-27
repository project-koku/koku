# COST-8142 Sources Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return fresh ingestion and cost-model metadata from the exact same `/sources/` URL without full-tenant Redis scans or repeated recomputation of 190+ providers.

**Architecture:** Cache the fully assembled filtered/paginated response and its page/provider generation vector. A hot read returns that snapshot after one batched generation check. A changed provider is refreshed from a per-provider detail cache and patched into the response. Advance only affected generations after committed writes. Keep the legacy full-response cache behind the off branch of an enablement flag during rollout.

**Tech Stack:** Django 5, Django REST Framework, PostgreSQL, django-redis/Valkey, django-tenants, Unleash, Django tests.

**Spec:** `docs/superpowers/specs/2026-10-17-cost-8142-sources-cache-design.md`

## Global Constraints

- The endpoint and all response fields remain unchanged; no migration or UI change.
- The new path is gated behind `cost-management.backend.sources_list_granular_cache`, with `dev_fallback=True` and production default off.
- No `KEYS` or `SCAN` is called by a write on the enabled path.
- Source and cost-model edits and display-relevant manifest changes refresh after commit; unrelated provider details remain hot.
- The local scale check uses 200 actual API-visible sources: 10 existing Nise test sources plus 190 synthetic linked OCP sources without ingested reports.
- The user runs IQE manually; do not run IQE unless asked.

---

## File map

- `koku/sources/cache.py`: versioned cache keys, batched page/detail reads, bounded cold-fill coordination, fail-open behavior, cache metrics.
- `koku/sources/cache_events.py`: exact post-commit generation changes and tenant/schema context.
- `koku/sources/api/view.py`: flag split, page assembly, legacy full-response cache wrapper, source CRUD invalidation calls.
- `koku/sources/test/api/test_granular_cache.py`: response parity, pagination/RBAC isolation, freshness, and fixed-query batch fill.
- `koku/sources/test/test_cache_events.py`: generations, transaction rollback, and no keyspace scan.
- `koku/api/provider/provider_manager.py` and `provider_builder.py`: provider/source lifecycle events.
- `koku/reporting_common/models.py` and `koku/masu/database/report_manifest_db_accessor.py`: manifest create/delete and relevant state/completion events.
- `koku/cost_models/models.py` and `cost_model_manager.py`: association and rename events.
- `koku/masu/processor/__init__.py`: rollout flag constant.
- `docs/architecture/sources-and-data-ingestion.md`: cache ownership and invalidation behavior.

### Task 1: Cache primitives and transaction-safe events

**Files:** Create `koku/sources/cache.py`, `koku/sources/cache_events.py`, `koku/sources/test/test_cache_events.py`.

**Interfaces:** `get_generation(schema: str, scope: str) -> str | None`, `advance_source_page(schema: str) -> None`, `advance_provider(schema: str, provider_uuid: UUID | str) -> None`, and `advance_provider_on_commit(schema: str, provider_uuid: UUID | str) -> None`. `None` from `get_generation` means bypass cache. All cache access uses a consistent explicit tenant schema context. `advance_*` is a fixed number of Redis operations and does not enumerate keys.

- [ ] **Step 1: Write failing tests.** In `test_cache_events.py`, use a real `LocMemCache` override and `schema_context(self.schema_name)`. Assert that advancing provider A changes only A's generation; page generation remains the same. Assert `captureOnCommitCallbacks(execute=False)` leaves generation unchanged before callback, `execute=True` changes it, and rollback does not. Patch `koku.cache.invalidate_cache_for_tenant_and_cache_key` to raise if called on the new path.
- [ ] **Step 2: Run red.** `pipenv run python koku/manage.py test sources.test.test_cache_events --no-input -v 2`; expected failure: cache-event module/functions absent.
- [ ] **Step 3: Implement.** Use `caches[CacheEnum.api]` and replace each generation with an opaque UUID token via one `cache.set` operation. Initialize missing keys with `cache.add` and read back the resulting token, so eviction cannot make a stale snapshot compare equal to a default generation. Use namespaced schema/scope/provider keys. Wrap cache operations in `schema_context(schema)` and catch cache backend errors to log and bypass, never to serve a stale current-generation key. `transaction.on_commit` registers callbacks only after the owning DB write.
- [ ] **Step 4: Run green.** Run the same test module and confirm all tests pass; then commit the slice.

### Task 2: Two-level read path behind the flag

**Files:** Modify `koku/sources/api/view.py`, `koku/masu/processor/__init__.py`; expand `koku/sources/cache.py`; create `koku/sources/test/api/test_granular_cache.py`.

**Interfaces:** `get_or_fill_response(request, build_page, lookup_details, strip_secret, render) -> tuple[dict, bytes]`, `get_or_fill_details(schema: str, tenant, uuids: list) -> dict[str, dict]`. The outer key includes schema, full URL/query, renderer/Accept, user UUID/admin state, and a stable digest of RBAC source access. The outer value holds a tenant epoch, page/provider generations, assembled response, and rendered body. A hot read uses one batched snapshot/epoch lookup; a changed epoch triggers a batched provider-generation comparison. Detail keys include schema, provider UUID, generation, and month boundary; reads use `get_many`, fills use `set_many`, and misses call `bulk_source_details` once.

- [ ] **Step 1: Write failing API tests.** Populate two OCP sources and a manifest/cost model. With the flag patched ON, call the identical list URL twice; assert response parity with the legacy path, one page build, one bulk detail fill, and no response reassembly or duplicate DB work on the second call. Change one provider's generation and assert only that provider is refilled while both sources remain on the page. Include `limit`/`offset`, source filters, a user with restricted source visibility, unlinked source, and a source with a secret in authentication; assert no cross-user data or secret leakage.
- [ ] **Step 2: Run red.** `pipenv run python koku/manage.py test sources.test.api.test_granular_cache --no-input -v 2`; expected failures are stale values and missing new-path calls.
- [ ] **Step 3: Implement.** Move the current `cache_page` decoration to a legacy-only method so it cannot intercept enabled requests. In enabled `list`, use `super().list` only on a missing/stale page generation. Store a complete response snapshot and generation vector. On unchanged reads, check generations in one batch and return the response without merging provider details. On a provider generation change, refresh and patch only that provider. Populate missing details via one `bulk_source_details` call; cache explicit unlinked defaults. Bound both layers' TTL by one hour and the next UTC month boundary. Use short `cache.add` fill locks and bounded wait/recheck; on timeout or cache error use DB without an API error. Add the flag constant and local development fallback.
- [ ] **Step 4: Run green.** Run the test module and existing `sources.test.api.test_view_bulk_details`, then commit the slice.

### Task 3: Targeted write events and legacy compatibility

**Files:** Modify `koku/sources/cache_events.py`, `koku/sources/api/view.py`, `koku/api/provider/provider_builder.py`, `koku/api/provider/provider_manager.py`, `koku/reporting_common/models.py`, `koku/masu/database/report_manifest_db_accessor.py`, `koku/cost_models/models.py`, `koku/cost_models/cost_model_manager.py`; expand tests in the two new modules.

**Interfaces:** `source_cache_changed(schema, *, page=False, provider_uuid=None, include_dependents=False)` advances generations after commit when the flag is ON and retains the pre-existing scan for source/provider lifecycle events when OFF. `dynamic_source_changed_on_commit(schema, provider_uuid, include_dependents=False)` is inert on the legacy path. `CostModelMap` events use the current tenant schema; public manifest events obtain schema from `manifest.provider.customer` and enter it explicitly for cache operations. A batch generation write updates the tenant epoch and all affected page/provider tokens together.

- [ ] **Step 1: Write failing freshness tests.** Prime one URL, then create/finish a manifest and confirm `status`, `has_data`, current/previous-month flags update on that same URL after commit. Prime cost models, detach/reattach and rename, and assert the same URL changes immediately. Assert source rename/create/delete affect the static layer; irrelevant `num_total_files` and `report_tracker` saves do not advance provider generation. Assert rollback does not advance; provider/infrastructure changes refresh affected dependents only.
- [ ] **Step 2: Run red.** Run `sources.test.api.test_granular_cache sources.test.test_cache_events`; expected failures show the old cached state after writes.
- [ ] **Step 3: Implement.** Replace the existing `/sources/` invalidation call sites with `source_cache_changed`. Use post-save/delete hooks for manifest creation/deletion and cost-model maps; the accessor's state/completion `save()` calls must activate those hooks, including `save(update_fields=["completed_datetime"])`. Use name-change detection for cost models. Ensure callbacks run after commit and do not send an event for housekeeping saves. Keep manifest/cost-model events inert when the flag is OFF. Explicitly handle any bulk write that bypasses signals on these fields.
- [ ] **Step 4: Run green.** Run focused source, provider, manifest, and cost-model tests; inspect SQL query counts for a 1-provider miss versus a 200-provider miss; commit the slice.

### Task 4: Scale, parity, observability, and rollout evidence

**Files:** Modify `koku/sources/cache.py`, `docs/architecture/sources-and-data-ingestion.md`; add focused assertions in `test_granular_cache.py`.

**Interfaces:** Metrics report page/detail hit/miss, fill duration, changed generation by event kind, and cache error counts. Labels are bounded; provider UUID and tenant are never metric labels.

- [ ] **Step 1: Write failing measurements/tests.** Assert cache misses call `bulk_source_details` once for the missing batch, subsequent calls do not query dynamic tables, and simultaneous cold callers do not each run the bulk query. Assert response digests match the legacy path for unchanged data.
- [ ] **Step 2: Run red.** Run the new granular cache tests; expected failure is extra duplicate fills or missing counters.
- [ ] **Step 3: Implement and document.** Add bounded metrics following nearby Koku patterns and explain the two layers, event ownership, safety TTL, flag, and rollback in the architecture doc.
- [ ] **Step 4: Run green.** Run focused Django tests, `git diff --check`, and applicable pre-commit checks. Then run the read-only `benchmark_sources_list.py` in warm, 5 ms, 250 ms, and cold-burst modes against the actual 200-source tenant; compare with the spec's baseline and run a one-provider churn test. If p95 misses the spec gate, profile and revise before calling the change complete. Do not run IQE; give the user its command. Commit only after these checks pass.
