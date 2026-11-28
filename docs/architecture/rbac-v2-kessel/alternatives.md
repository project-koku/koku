# Alternative approaches and cross-project evidence

Options considered for moving Cost Management off RBAC v1, with the evidence gathered from other services so we can argue the trade-offs rather than the preference.

Companion docs: [design](README.md) · [v1 → v2 mapping](v1-to-v2-mapping.md).

## Options at a glance

| Approach | Grants stored in | Kessel in the Cost path | What Cost must build | Main blocker |
|---|---|---|---|---|
| **A. RBAC v1** (status quo) | RBAC v1 policies + resource definitions | no | nothing | v1 is being decommissioned in SaaS |
| **B. v2 grant store** (adopted) | RBAC v2 roles + role bindings | no (replication target only) | v2 client, workspace mapping, local evaluation | platform must allow Cost permissions in v2 roles |
| **C. Outbox + Kessel reporting** (deferred) | Kessel relations / Inventory | yes | outbox, relay, schema, resource reporting | no `source` type, schema work, no consumer |
| **D. Workspace-only phase 0** (KSL-75) | RBAC v2 workspaces | yes, workspace check | workspace mapping only | coarser: loses per-account/cluster narrowing |
| **E. rbac-mini in SaaS** | Cost-owned tables | no | BOP/IT adapter, v1 surface, self-authz | identity must come from BOP/IT, which Cost cannot integrate |

## A. RBAC v1 `/access/` (status quo)

`GET /api/rbac/v1/access/?application=cost-management` returns ACLs with resource definitions; koku flattens them into `user.access` and filters reports (`koku/rbac.py`).

Cheapest today, but the endpoint is a bridge: for orgs opted into v2 it returns `400 V2 orgs may only query applications in the allowed list` once the app leaves `V2_MIGRATION_APP_EXCLUDE_LIST`.

## B. RBAC v2 grant store (adopted)

RBAC v2 owns users, groups, roles, and bindings; Cost reads bindings for the caller, expands role permissions, and evaluates locally against an `object → workspace_id` mapping. Kessel only receives the replicated tuples; Cost never calls `Check` on the report path.

Why it wins for us:

- it removes the v1 dependency without putting Kessel on the request path;
- users/groups/grants come from the platform, which is the only place that may talk to BOP/IT;
- Cost keeps its permission semantics, so report filtering and the OCP-on-AWS intersection are unchanged;
- no outbox, no resource reporting, no `cost-management.ksl` for our own objects.

Constraints are documented in the design's platform asks: tenant opt-in is irreversible, `cost-management` is still in the v2 role exclude list, the v2 management API itself needs Inventory, and the S2S read path is undocumented.

## C. Transactional outbox + Kessel resource reporting (deferred)

The original design: Cost owns tuples for its objects and syncs them to Kessel.

Write path:

- an `outbox` table in the Cost database, written in the same transaction as the Cost change;
- a relay claims rows with `SELECT … FOR UPDATE SKIP LOCKED`, writes/upserts tuples, marks dispatched;
- idempotent writes, tombstones on delete, backfill for existing objects, periodic reconciler against `ReadTuples`;
- failure policy: stale authorization, not failed Cost writes; alert on relay lag.

Platform split (important, and easy to get wrong):

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `outbox.event.kessel.tuples` | resource owners (HBI today) | `kessel-inventory-consumer` | report resources into Inventory |
| `outbox.event.relations-replication-event` | RBAC only | RBAC Kafka consumer | replicate authorization relations |

Cost writing RBAC-owned relation tuples would make us a second writer of RBAC's model; resource reporting belongs on the Inventory contract.

What it would require beyond the current work:

- a `source` (or Cost-specific) resource type in `inventory-api`, with reporter config and JSON schema;
- KSL/KSIL changes in `rbac-config` so the type and permissions are checkable (`cost-management.ksl`, `add_v1_based_permission`, and the missing `t_binding->` wiring);
- the topic added to the inventory consumer's topic list;
- a decision on who reports sources — the Sources service owns them, and `sources-api-go` has no Kessel code today.

Why deferred: no consumer needs per-source authorization from Kessel yet (sources-ui uses RBAC v2 workspaces), the resource type does not exist, and it would not remove local evaluation — the granular Cost decision stays ours either way. It becomes worthwhile if another service must answer "which Cost resources can this user see", or if Cost must answer resource-level checks in Kessel.

## D. Workspace-only phase 0 (KSL-75)

Kessel keeps the workspace hierarchy; Cost stores the `resource ↔ workspace` mapping, reports no resources, and checks only "may this subject act on this workspace?". This is a subset of option B — same v2 API, but without reading role permissions and evaluating them locally.

It is the fallback if v2 custom roles cannot carry Cost permissions: correctness by workspace, at the cost of losing per-account/cluster narrowing (everyone bound to a workspace sees all objects in it).

## E. rbac-mini in SaaS (excluded)

A self-contained RBAC (Go, v1-compatible) would remove the platform dependency entirely, but it cannot be the SaaS authority: users, service accounts, groups, and org admin state must come from BOP/IT, and Cost is not allowed to integrate with either. Without identity it can only be a credential store for a directory it does not own. It stays the on-prem v1 floor.

## What other teams do

### Host Inventory is the reference outbox producer

- ClowdApp `optionalDependencies`: `kessel-inventory`, `kessel-relations`, `kessel-kafkaconnect`, `kessel-inventory-consumer`; Kessel auth via `kessel-auth-secret`; `BYPASS_KESSEL` for local/dev.
- `lib/outbox_repository.py` writes `{aggregateid, aggregatetype, operation: ReportResource|DeleteResource, version: v1beta2, payload}` inside the caller's transaction. Payload: `type`, `reporter_type`, `reporter_instance_id`, `representations.metadata` (`local_resource_id`, hrefs, reporter version, `transaction_id`), `representations.common.workspace_id`, `representations.reporter`. Deletes use a `reference` object.
- It flushes and then deletes the row in the **same transaction**, relying on Debezium reading the WAL. A polling relay must instead keep the row until dispatched.
- `platform-mq` defines `outbox.event.kessel.tuples` (1 partition, RF 3, `min.insync.replicas=2`, 7-day retention).

### Permission consumers (no outbox)

- `rhsm-subscriptions` (swatch-api/tally/utilization) declares `kessel-inventory` and reads `KESSEL_ENDPOINT`.
- `ros-backend` defaults `KESSEL_URL` to `kessel-inventory-api:9000`.
- `compliance-backend`, `notifications-backend`, `insights-remediations`, `digital-roadmap-backend`, `vulnerability-engine`, `playbook-dispatcher` all point at `kessel-inventory-api:9000`; most mount the shared `kessel-auth-secret`.
- `playbook-dispatcher` has an Inventory client with `ReportResource`/check methods; `vulnerability-engine` also declares `kessel-relations`.

### RBAC v2 API clients

- `/api/rbac/v2/workspaces/?type=default`: patchman-engine, notifications-frontend, sources-ui, subscription-central-ui, ros-frontend, HBI middleware.
- `/api/rbac/v2/role-bindings/` (and `by-subject`): insights-rbac-ui.
- `/api/rbac/v2/check/self` (bulk check): notifications-frontend.
- The migration switch is the `platform.rbac.workspaces` Unleash flag (insights-chrome, compliance-frontend, sources-ui, HBI's `FLAG_RBAC_WORKSPACES`). sources-ui documents the v1↔v2 hybrid explicitly (`RBAC_V2_MIGRATION.md`, `HYBRID_RBAC_SUMMARY.md`).

### Takeaways

- HBI is the only resource-outbox producer found for `outbox.event.kessel.tuples`; everyone else either consumes Kessel checks or the v2 RBAC API.
- `outbox.event.relations-replication-event` has no producer outside RBAC — Cost should not become one.
- The migration pattern across projects is a **flag-gated hybrid**: keep v1 while the flag is off, switch callers to v2 when it is on, with `BYPASS_KESSEL` as the local escape hatch.
- That pattern is exactly what the current PR implements for koku (`RBAC_BACKEND`, default v1), minus the per-tenant flag.

## Comparison on the criteria that matter to us

| Criterion | A v1 | B v2 grants | C outbox | D workspace-only | E rbac-mini |
|---|---|---|---|---|---|
| Identity from BOP/IT | yes (platform) | yes (platform) | yes (platform) | yes | **no** |
| Per-account/cluster narrowing | yes (RDs) | yes (workspaces + permissions) | yes (tuples) | coarse (workspace only) | yes |
| New platform schema work | none | v2 role catalog for Cost | resource type + KSL + topic | none | none |
| Kessel on request path | no | **no** | yes (Check) | yes (workspace check) | no |
| Rollback after cutover | n/a | **no** (opt-in is one-way) | n/a | no | n/a |
| Effort | none | medium | high | low | high |
| Fits the platform direction | no | yes | yes | partly | no |

## Recommendation

Adopt **B** now, keep **D** as the fallback if the v2 role catalog cannot carry Cost permissions, and keep **C** as the later phase for resource-level checks. **A** is only a transition; **E** is excluded by the identity constraint.

## Open questions carried from the research

- Does phase 0 need any Cost-owned tuples at all, or only the local mapping table?
- Which object becomes the Kessel resource: workspace only, or provider/cluster/node/project/cost model later?
- Resource reporting via Inventory `ReportResource`, or direct relation writes?
- What is the concrete schema? The referenced branch is `project-kessel/starlark-unified-schema`, `cost-management-hierarchy-option`.
- On-prem has no Kessel instance; every option that needs one is SaaS-only.
