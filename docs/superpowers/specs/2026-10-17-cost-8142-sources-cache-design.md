# COST-8142: fresh `/sources/` metadata without tenant-wide cache churn

## Decision and scope

Replace the legacy cache with two cached layers: a fully assembled response
snapshot and dynamic details keyed by individual provider. On a hot request,
compare the snapshot's tenant epoch in the same batched read and return it
without rebuilding 200 source rows. When the epoch changes, compare the page
and provider generations in one batched read. A committed write changes only
the relevant generation;
no manifest or cost-model write scans Redis or forces every source in a tenant
to be recomputed. This is a backend-only change. The endpoint and its response
fields remain unchanged.

This design addresses the two COST-8142 reproducers: completed ingestion must
update `status`/data flags, and cost-model attachment, detachment, reassignment,
and rename must update `cost_models`. It does not infer customer ingestion state
from a local synthetic benchmark, and it does not change UI polling behavior.

## Current behavior and why the prior fix was reverted

[`SourcesViewSet.list`](../../../koku/sources/api/view.py) caches the complete
response for `CACHE_MIDDLEWARE_SECONDS` (3600 by default). The cached response
contains both [`Sources` fields](../../../koku/api/provider/models.py) and
[`bulk_source_details`](../../../koku/api/provider/provider_manager.py), so
changes in manifests or tenant-schema cost-model maps remain invisible on that
URL. Changing a query parameter bypasses the stale entry, matching the IQE
reproducer. Existing source/provider invalidation calls
[`invalidate_cache_for_tenant_and_cache_key`](../../../koku/koku/cache.py),
which enumerates the entire Redis keyspace. Repeating that operation on every
manifest save, as in reverted PR #6316, makes frequent automated reads cold.
The merged bulk query path reduces database query count but does not fix cache
freshness by itself.

## Read path

1. Build a complete response snapshot from the existing filtered, ordered,
   paginated `SourcesSerializer` result and provider details. Cache its page
   generation, per-provider generation vector, and tenant epoch alongside the response for
   one hour. Its key includes tenant schema,
   the complete normalized query string, renderer/`Accept`, and a fingerprint
   of the authenticated user's source visibility. Do not cache a response for
   one permission set under another user's key. Preserve pagination and filter
   behavior, including pages with no sources.
2. On each request, batch-read the snapshot and tenant epoch. If the epoch
   matches, return the stored response directly. On a changed epoch, batch-read
   the page/provider generations. If the page generation differs, rebuild the page and refresh its
   provider details. If only provider generations differ, refresh and patch
   those providers in the snapshot, leaving all others untouched.
3. For changed UUIDs, fetch dynamic details with a batched cache read.
   Keys include tenant schema, provider UUID, and provider generation. For
   missing entries, call `bulk_source_details(missing_uuids, tenant)` once,
   then populate those entries in a batch. An unlinked source has an explicit
   cached fallback from `unlinked_source_details` so it is not queried forever.
   Keep the current secret-stripping and response shape.
4. Preserve source order, pagination, secret stripping, and response shape.
   Replacing a provider's details must also remove stale dynamic fields from
   the old snapshot when they disappear.
5. Use short, bounded locks for simultaneous cold fills of the same page or
   provider batch. A waiter rechecks cache and may compute from the database if
   the lock holder fails. A cache outage falls back to the existing database
   path. Do not serve stale data indefinitely or turn a cache failure into an
   API failure.

Generation tokens and the tenant epoch are replaced together in Redis *after the database commit*.
Readers compare the stored snapshot vector with current tokens; a read that
began before the commit cannot stamp old data with a new token. Missing tokens
are initialized with unique values rather than a default zero, so eviction
cannot make an old snapshot compare equal. Old detail entries expire naturally;
no `KEYS`/`SCAN` operation is required. Explicit schema
context is required for cache operations made by public-schema ingestion code,
because the current API cache uses `django_tenants.cache.make_key`. If a
generation key is unavailable, bypass that layer until the cache is healthy.

Provider details have a one-hour safety TTL, capped at the next UTC month
boundary because current/previous-month flags are time-dependent. The TTL is a
recovery bound for a missed event, not the normal freshness mechanism. A newly
started request after a successful commit and generation change should see the
new value immediately. In-flight requests may finish with their pre-commit
snapshot.

## Write path and exact invalidation

| Committed change | Cache action | Reason |
| --- | --- | --- |
| Source create/delete, rename, credentials, type, reference, or visibility | Advance that tenant's static-list generation; advance the linked provider generation only when provider-owned details changed | Static fields, ordering, filters, or membership may change |
| Provider fields represented in dynamic details, including infrastructure | Advance that provider's generation | One source's dynamic output changes |
| Manifest created, display-relevant state transition, completion, or deletion | Advance its provider's generation once per committed transition | Latest status and data flags change; ignore unrelated file-count or archive housekeeping saves |
| Cost-model map create/delete/reassignment | Advance the old and new provider generations after commit | Associations change without a source row change |
| Cost-model name change | Advance generations of its mapped providers after commit | `cost_models[].name` changes without a map-row change |

Events must be connected to the real mutation paths, including
[`ReportManifestDBAccessor`](../../../koku/masu/database/report_manifest_db_accessor.py),
[`CostModelManager`](../../../koku/cost_models/cost_model_manager.py), and
provider/source lifecycle handlers. Tests must cover `update_fields`, bulk
operations, transaction rollback, and provider deletion. Where a bulk write
bypasses Django signals, invalidate explicitly at that write site. Advancing a
generation must not run a tenant-wide keyspace scan. Source status or provider
changes represented inside dependent OCP infrastructure details must refresh
those OCP provider entries. Identify dependents from
`ProviderInfrastructureMap` rather than flushing the tenant.

## Validation gate and rollout

The existing local Nise test tenant (`org1234567`) has 10 sources with test
data. For this design review, 190 additional, clearly named OCP `Sources` and
linked `Provider` rows were created in the same local tenant; the live API
returned **200** sources with `limit=1000`. The extra 190 are synthetic source
records without ingested reports. This validates list cardinality, not
190 simultaneous ingestion pipelines. Use Nise ingestion on at least one
linked OCP source to test the before/after data flags and status while the
200-source list is under load.

Baseline from commit `d68fd1ff3` on 2026-10-17, using
`benchmark_sources_list.py`, 200 actual API-visible sources, bulk-list enabled:

| Scenario | Calls | Failures | p50 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Warm cache, 5 ms interval, concurrency 4 | 120 | 0 | 5.88 ms | 11.27 ms | 20.36 ms |
| New key, 5 ms interval, concurrency 4 | 120 | 0 | 13.64 ms | 94.06 ms | 178.14 ms |
| New key, 250 ms interval, concurrency 4 | 120 | 0 | 17.40 ms | 25.60 ms | 60.32 ms |
| Cold burst, concurrency 8 | 32 | 0 | 27.68 ms | 247.92 ms | 248.57 ms |

Before rollout, rerun all four modes on the same 200-source database and
machine after each code revision. Compare p50/p95/p99, failures, source count,
response digest, and cache hit/miss counters. For the hot path, use an initial
gate of no errors and p95 no more than the baseline plus 10 ms; for burst and
churn, require no timeouts and no worse p95 than baseline. A result outside
these gates requires profiling/revising the design rather than declaring the
cache fix successful. Repeat in an ephemeral environment with at least 190
actual sources and a realistic request rate before enabling a new cache path
globally. The local numbers are directional, not production SLOs.

The local candidate on 2026-10-17 returned the same response fingerprint as
the baseline for all 200 sources, with zero failures:

| Scenario | Baseline p95 | Candidate p95 | Calls |
| --- | ---: | ---: | ---: |
| Warm, 5 ms interval, concurrency 4 | 11.27 ms | 7.51 / 9.71 / 11.52 ms (repeats) | 120 each |
| Fresh key, 5 ms interval, concurrency 4 | 94.06 ms | 57.90 ms | 120 |
| Fresh key, 250 ms interval, concurrency 4 | 25.60 ms | 25.28 ms | 120 |
| Cold burst, concurrency 8 | 247.92 ms | 95.51 / 101.37 / 137.25 ms (repeats) | 32 each |
| One provider generation changed, then 8-way burst | No freshness path | 99.43 ms | 32 |

The live API response digest matched throughout. These measurements use 10
Nise-backed sources plus 190 linked synthetic source rows; they demonstrate
list-scale behavior and targeted refresh, not 190 concurrent ingestion streams.
Earlier measurements varied substantially while the implementation and local
server were changing. Reproduce on the intended deployment image and a
representative ephemeral tenant before rollout.

Freshness checks: (1) read the same exact `/sources/?limit=1000` URL before
and after a Nise-backed manifest completes; verify the target source's status
and data flags change, (2) run the IQE cost-model detach/reassign reproducer,
(3) rename a cost model and verify its new name, (4) exercise source edits and
RBAC isolation, and (5) send frequent reads during multiple manifest updates
to confirm unaffected providers remain hot. The user will run IQE manually:

```bash
ENV_FOR_DYNACONF=local iqe tests plugin cost_management -k "test_api_cost_model_cost_sources_invalidates_cache" -raA --pdb
```

Gate the new path behind a backend enablement flag with local fallback on and
production default off, following [`unleash-flags.md`](../../../docs/agent/unleash-flags.md).
Keep the legacy path during rollout. Record per-layer hit rates, fill duration,
missing-provider count, generation changes by page/provider scope, and cache errors;
avoid high-cardinality provider labels. Verify parity and latency on selected
ephemeral/stage tenants before broad enablement. No API contract or migration
change is expected.

## UI handoff observation

The UI Overview OCP tab uses `current_month_data || previous_month_data` to
choose between charts and “Still processing”; `has_data=true` alone is not
sufficient. An already open tab may also lack a timely refetch after ingestion.
The backend fix can guarantee that a *new request* returns fresh data, but
cannot make an idle browser issue that request. If a fresh `/sources/` response
has current/previous-month data and the UI still shows the message, hand off
the request/refetch path to the UI team. If only older data exists, discuss the
product meaning of the message with them; do not silently change backend flags.
