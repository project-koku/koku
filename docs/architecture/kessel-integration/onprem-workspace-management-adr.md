# ADR: On-Prem Workspace Management for Kessel Authorization

**Date**: 2026-03-02
**Status**: Proposed
**Authors**: Cost Management On-Prem Team
**Reviewers**: Kessel Team, Cost Management SaaS Team
**Related**: [kessel-ocp-integration.md](./kessel-ocp-integration.md), [FLPATH-3294](https://issues.redhat.com/browse/FLPATH-3294), [FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)

---

## Table of Contents

- [Context](#context)
- [Problem Statement](#problem-statement)
- [Constraints](#constraints)
- [Decision](#decision)
- [Architecture Overview](#architecture-overview)
  - [Layer Separation](#layer-separation)
  - [Permission Resolution Flow](#permission-resolution-flow)
  - [Default Visibility Model](#default-visibility-model)
  - [Team-Based Access Grants](#team-based-access-grants)
  - [Cross-Team Resource Sharing](#cross-team-resource-sharing)
- [Workspace Hierarchy Design](#workspace-hierarchy-design)
- [Tuple Management: Who Writes What](#tuple-management-who-writes-what)
- [Re-Ingestion Safety](#re-ingestion-safety)
- [Resource Deletion and Multi-Workspace Cleanup](#resource-deletion-and-multi-workspace-cleanup)
- [Why Direct SpiceDB for Admin Operations](#why-direct-spicedb-for-admin-operations)
- [SaaS Compatibility Analysis](#saas-compatibility-analysis)
- [Alternatives Considered](#alternatives-considered)
- [Risks and Mitigations](#risks-and-mitigations)
- [Implementation Status](#implementation-status)
- [Open Questions](#open-questions)

---

## Context

Koku's on-prem deployment uses [Kessel](https://github.com/project-kessel) as its authorization backend, replacing the SaaS RBAC service that is not available outside cloud.redhat.com. The Kessel stack consists of:

- **SpiceDB**: The authorization engine (Zanzibar-inspired relationship-based access control)
- **Kessel Inventory API**: gRPC service for resource metadata and authorization queries (`Check`, `StreamedListObjects`, `ReportResource`, `DeleteResource`)
- **Kessel Relations API**: REST service for SpiceDB tuple management (create/delete relationships)

Koku's `KesselAccessProvider` ([access_provider.py](../../../koku/koku_rebac/access_provider.py)) queries the Inventory API to determine what resources a user can see. Koku's `resource_reporter` ([resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py)) registers resources and creates SpiceDB `t_workspace` tuples that make resources discoverable.

The [ZED schema](../../../dev/kessel/schema.zed) defines the authorization model: resources belong to workspaces via `t_workspace` tuples, users are bound to workspaces via `role_binding` tuples, and permissions are computed by traversing these relationships.

**The missing piece**: how on-prem administrators manage **who can see which resources**. The current implementation assigns all resources to a single org-level workspace, making everything visible to all users with any role binding at that workspace. There is no mechanism for per-team or per-resource access control.

---

## Problem Statement

On-prem customers need the ability to:

1. **Restrict resource visibility** — Team A should see clusters A and B, Team B should see clusters B and C, admin should see all.
2. **Grant access via groups** — Access managed through Keycloak groups, not individual user tuples.
3. **Survive data re-ingestion** — When Koku processes new data for an existing cluster, it must not overwrite custom access assignments.
4. **Cross-team sharing** — A single resource must be visible to multiple teams without workspace hierarchy explosion.

These requirements must be met **without changing Koku's application layer** (`access_provider.py`, views, serializers, middleware), which must remain SaaS-compatible.

---

## Constraints

| Constraint | Rationale |
|---|---|
| **Koku's `KesselAccessProvider` must be unchanged** | Same code runs in SaaS and on-prem. It calls `StreamedListObjects` and `Check` — it must not know about workspace topology. |
| **ZED schema must be compatible with upstream `rbac-config`** | No new `definition` or `relation` types. The on-prem schema is the canonical schema plus resource type definitions ([FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)). |
| **One `workspace_id` per resource in Kessel Inventory API** | `ReportResource` accepts a single `workspace_id` in representations. The Inventory API's contract is one workspace per resource. |
| **SpiceDB allows multiple `t_workspace` tuples per resource** | SpiceDB itself has no single-workspace constraint. Multiple `t_workspace` tuples are valid and permission resolution uses union (`+`). |
| **On-prem does not use Kessel's CDC pipeline** | The CDC-to-consumer pipeline that automatically creates tuples from Inventory API events is disabled on-prem. Koku writes tuples directly. |

---

## Decision

**Team Workspaces with Inheritance + Keycloak-Driven Automation + Direct SpiceDB for Admin Operations.**

Specifically:

1. **Workspace hierarchy**: Create team workspaces as children of the org-level workspace. Resources are assigned to team workspaces. Workspace inheritance (`t_parent`) grants admin visibility into all child workspaces.

2. **Default visibility**: New resources are assigned to the org-level workspace by `resource_reporter.py`. Only users bound at the org-level workspace (admins) see newly registered resources. Regular users are bound at team workspaces and do not inherit upward.

3. **Team-based grants**: Admin assigns resources to team workspace(s) by writing `t_workspace` tuples directly to SpiceDB. Team members (bound at the team workspace via `role_binding`) can then see those resources.

4. **Cross-team sharing**: A resource can have multiple `t_workspace` tuples (one per team workspace). This exceeds Kessel Inventory API's single-workspace contract but is valid in SpiceDB. The additional tuples are managed by the admin tooling, not by Koku's `resource_reporter`.

5. **Re-ingestion safety**: The `org_id` comes from the cost management metrics operator and is immutable for a given cluster. Since `resource_reporter.py` always upserts the primary `t_workspace` tuple using the same `org_id`, re-ingestion is inherently idempotent. Admin-managed additional tuples (team workspace assignments) are never touched by `resource_reporter`.

6. **Keycloak automation**: On-prem admin tooling syncs Keycloak groups to SpiceDB: group creation → workspace + role_binding creation, group membership changes → `t_subject` tuple updates.

---

## Architecture Overview

### Layer Separation

```
┌─────────────────────────────────────────────────────────────┐
│                    KOKU APPLICATION LAYER                     │
│                                                               │
│  Views / Serializers / Middleware                             │
│       │                                                       │
│       ▼                                                       │
│  KesselAccessProvider (access_provider.py)                    │
│       │  StreamedListObjects()  →  list of resource IDs      │
│       │  Check()                →  wildcard or denied         │
│       ▼                                                       │
│  Kessel Inventory API (gRPC)                                 │
│                                                               │
│  ┄┄┄┄┄┄┄┄┄  SaaS-compatible boundary  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄   │
│                                                               │
│  resource_reporter.py                                        │
│       │  ReportResource()       →  Inventory API             │
│       │  t_workspace tuple      →  Relations API             │
│       │  (always uses org_id — idempotent on re-ingestion)   │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│              ON-PREM MANAGEMENT PLANE                         │
│                                                               │
│  Admin Tooling / Keycloak Automation                         │
│       │  Create/delete workspaces                            │
│       │  Create/delete role_bindings                         │
│       │  Assign resources to team workspaces (t_workspace)   │
│       │  Sync Keycloak groups to SpiceDB                     │
│       ▼                                                       │
│  SpiceDB (gRPC — direct, bypasses Relations API)             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

The SaaS-compatible boundary separates code that runs identically in both environments (above) from on-prem-specific admin operations (below). Koku's application layer has **zero awareness** of workspace topology, team workspaces, or Keycloak groups.

### Permission Resolution Flow

When Koku calls `StreamedListObjects` for a user, SpiceDB traverses the relationship graph:

```
StreamedListObjects(resource_type="openshift_cluster", subject="rbac/principal:redhat/alice")

SpiceDB resolves:
  For each cost_management/openshift_cluster:
    → follow t_workspace → rbac/workspace
      → check cost_management_openshift_cluster_read permission
        → t_binding → role_binding (does alice match t_subject?)
          → t_granted → role (does role have the permission?)
        → t_parent → parent workspace (inherit and check recursively)

Returns: [cluster IDs where alice has read permission]
```

This resolution is identical regardless of whether the `t_workspace` tuple was created by `resource_reporter.py` (via Relations API) or by admin tooling (via direct SpiceDB write). SpiceDB does not distinguish tuple origin.

### Default Visibility Model

```
                     ┌──────────────────────┐
                     │  rbac/tenant:org123   │
                     └──────────┬───────────┘
                                │ t_platform
                     ┌──────────▼───────────┐
                     │ rbac/workspace:org123 │ ← admin role_binding (admin-user)
                     │  (org-level default)  │
                     └──────────┬───────────┘
                           t_parent │
                    ┌───────────┴───────────┐
         ┌──────────▼──────────┐  ┌─────────▼──────────┐
         │ workspace:team-infra│  │workspace:team-fin   │
         │                     │  │                     │
         │ role_binding:       │  │ role_binding:       │
         │   infra-group       │  │   finance-group     │
         └─────────────────────┘  └─────────────────────┘
```

**On resource registration** (`on_resource_created`):

```
cost_management/openshift_cluster:new-cluster
    #t_workspace → rbac/workspace:org123
```

At this point:
- **admin-user** (bound at `workspace:org123`): **CAN** see `new-cluster`
- **infra-member** (bound at `workspace:team-infra`): **CANNOT** see `new-cluster`
- **finance-member** (bound at `workspace:team-fin`): **CANNOT** see `new-cluster`

Inheritance flows **downward** (parent permissions available in children), not upward (child bindings do not grant access to parent resources).

### Team-Based Access Grants

Admin assigns `new-cluster` to `team-infra`:

```
Admin tooling → SpiceDB WriteRelationships:
    cost_management/openshift_cluster:new-cluster
        #t_workspace → rbac/workspace:team-infra   (additional tuple)
```

Now:
- **admin-user**: **CAN** see `new-cluster` (via org123 tuple, unchanged)
- **infra-member**: **CAN** see `new-cluster` (via team-infra tuple)
- **finance-member**: **CANNOT** see `new-cluster`

The original `t_workspace → org123` tuple remains. The admin tuple is additive.

### Cross-Team Resource Sharing

Admin also grants finance access to `new-cluster`:

```
Admin tooling → SpiceDB WriteRelationships:
    cost_management/openshift_cluster:new-cluster
        #t_workspace → rbac/workspace:team-fin     (third tuple)
```

Now:
- **admin-user**: **CAN** see `new-cluster` (via org123)
- **infra-member**: **CAN** see `new-cluster` (via team-infra)
- **finance-member**: **CAN** see `new-cluster` (via team-fin)

The resource has three `t_workspace` tuples. SpiceDB resolves all paths. `StreamedListObjects` returns `new-cluster` for all three users.

---

## Workspace Hierarchy Design

### Relationship Chain

```
rbac/tenant:org123
    │
    └── rbac/workspace:org123  (t_platform → tenant)
            │
            ├── rbac/workspace:team-infra  (t_parent → workspace:org123)
            │       │
            │       └── rbac/role_binding:rb-infra
            │               t_granted → rbac/role:ocp-viewer
            │               t_subject → rbac/group:infra-group#member
            │
            ├── rbac/workspace:team-fin  (t_parent → workspace:org123)
            │       │
            │       └── rbac/role_binding:rb-fin
            │               t_granted → rbac/role:ocp-viewer
            │               t_subject → rbac/group:finance-group#member
            │
            └── rbac/role_binding:rb-admin
                    t_granted → rbac/role:cost-admin
                    t_subject → rbac/principal:redhat/admin-user
```

### Why Inheritance Works for Admin

When `new-cluster` has `t_workspace → workspace:org123`, SpiceDB checks:

```
workspace:org123.cost_management_openshift_cluster_read
    = t_binding->cost_management_openshift_cluster_read   (rb-admin grants this)
    + t_parent->cost_management_openshift_cluster_read    (tenant-level, if any)
```

Admin's `role_binding:rb-admin` at `workspace:org123` grants the permission. Resources in child workspaces are also visible to admin because children include `t_parent->cost_management_openshift_cluster_read` which resolves up to `workspace:org123` where admin is bound.

### Why Team Members Cannot See Org-Level Resources

When `new-cluster` has only `t_workspace → workspace:org123`, SpiceDB checks permissions **on `workspace:org123`** (not on `workspace:team-infra`). The infra-member's binding is at `workspace:team-infra`, which is a **child**, not the resource's workspace. Child bindings do not propagate to parents.

The infra-member gains access only when the resource has a `t_workspace → workspace:team-infra` tuple, at which point SpiceDB checks permissions on `workspace:team-infra` where the binding exists.

---

## Tuple Management: Who Writes What

| Tuple | Written by | Via | When | SaaS-compatible? |
|---|---|---|---|---|
| `resource #t_workspace → workspace:org123` | `resource_reporter.py` | Relations API | Resource creation / data ingestion | Yes |
| `resource #t_workspace → workspace:team-X` | Admin tooling | SpiceDB direct | Admin grants team access | On-prem only |
| `workspace:team-X #t_parent → workspace:org123` | Admin tooling | SpiceDB direct | Team workspace creation | On-prem only |
| `role_binding #t_granted → role` | Admin tooling | SpiceDB direct | Role assignment | On-prem only |
| `role_binding #t_subject → group#member` | Admin tooling / Keycloak sync | SpiceDB direct | Group binding | On-prem only |
| `group #t_member → principal` | Keycloak sync | SpiceDB direct | User added to group | On-prem only |

`resource_reporter.py` manages **only** the primary org-level `t_workspace` tuple. All workspace hierarchy, role bindings, and group management tuples are managed by the on-prem admin plane.

---

## Re-Ingestion Safety

When Koku processes new data for an existing cluster, `on_resource_created` is called again with the same `(resource_type, resource_id, org_id)`. The `org_id` comes from the **cost management metrics operator** running on the OCP cluster — it identifies which organization the cluster belongs to. This value is immutable: the same cluster always reports the same `org_id`.

### Why No Workspace Resolution Is Needed

The primary `t_workspace` tuple always uses `org_id` as the workspace. Since the metrics operator always sends the same `org_id` for a given cluster, re-ingestion upserts the identical tuple — effectively a no-op. There is no risk of overwriting a different workspace because the `org_id` never changes.

Admin-managed team workspace tuples (written directly to SpiceDB) are completely separate from the primary tuple. `resource_reporter.py` does not know about them, does not query for them, and never modifies them.

### What happens during re-ingestion

| Tuple | Written by | Re-ingestion behavior |
|---|---|---|
| `cluster #t_workspace → workspace:org123` | `resource_reporter.py` | Upsert with same `org_id` — **idempotent no-op** |
| `cluster #t_workspace → workspace:team-infra` | Admin tooling (SpiceDB direct) | **Untouched** — `resource_reporter` does not know about it |
| `cluster #t_workspace → workspace:team-fin` | Admin tooling (SpiceDB direct) | **Untouched** — `resource_reporter` does not know about it |

This separation is inherent to the architecture: `resource_reporter.py` manages the **org-level primary tuple** (deterministic, always `org_id`), and the **admin tooling manages team assignments** (additive tuples in SpiceDB). The two never conflict.

---

## Resource Deletion and Multi-Workspace Cleanup

When a resource's cost data is fully purged from PostgreSQL (retention expiry), `on_resource_deleted` removes the resource from both Kessel Inventory and SpiceDB. This must clean up **all** `t_workspace` tuples — including admin-managed ones for team workspaces — without needing to know which workspaces the resource was assigned to.

### How It Works

`_delete_resource_tuples()` in [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py#L316-L353) sends a filter-based DELETE to the Relations API:

```python
params = {
    "filter.resource_namespace": "cost_management",
    "filter.resource_type": resource_type,
    "filter.resource_id": resource_id,
    "filter.relation": "t_workspace",
}
# DELETE /api/authz/v1beta1/tuples?filter.*=...
```

The filter matches on `resource_namespace + resource_type + resource_id + relation` but does **not** specify a subject (workspace). This means the DELETE removes **every** `t_workspace` tuple for that resource, regardless of which workspace it points to.

### Deletion Sequence

```
on_resource_deleted("openshift_cluster", "cluster-prod", "org123")
│
├─ 1. DeleteResource (Inventory API gRPC)
│     Removes resource metadata from Kessel Inventory database.
│
├─ 2. _delete_resource_tuples("openshift_cluster", "cluster-prod")
│     Relations API DELETE with filter-by-resource-id.
│     Removes ALL t_workspace tuples:
│       ✗  cluster-prod #t_workspace → workspace:org123      (primary, written by resource_reporter)
│       ✗  cluster-prod #t_workspace → workspace:team-infra  (admin-managed)
│       ✗  cluster-prod #t_workspace → workspace:team-fin    (admin-managed)
│
└─ 3. KesselSyncedResource.delete()
      Removes the tracking row from Koku's database.
```

### Why This Is Correct

- **The resource no longer exists in Koku's data.** Once cost data is purged from PostgreSQL, there is nothing to query or display. The resource should not be discoverable by any user in any workspace.
- **No enumeration needed.** The filter-based DELETE handles any number of workspace assignments without Koku needing to track which workspaces the admin assigned. One API call cleans up everything.
- **Same behavior for orphan cleanup.** `cleanup_orphaned_kessel_resources()` follows the same pattern — iterates tracked resources for a provider and calls `_delete_resource_tuples` for each, which removes all workspace assignments.

### When Deletion Does NOT Happen

`on_resource_deleted` fires only when cost data is **fully purged** (retention expiry after a source has been deleted). It does **not** fire when:

- A source is deleted (historical data must remain queryable until retention expires)
- Data is re-processed or corrected
- An admin removes the resource from a specific workspace (that's a targeted tuple delete via admin tooling, not resource deletion)

This distinction is important: **admin workspace management (adding/removing team assignments) is separate from resource lifecycle (creation/deletion)**. Admin operations modify individual `t_workspace` tuples. Resource deletion removes the resource entirely.

---

## Why Direct SpiceDB for Admin Operations

The Kessel Relations API is a REST-to-gRPC translator for SpiceDB tuple CRUD. On-prem, it provides:

| Feature | Relations API | SpiceDB Direct |
|---|---|---|
| Tuple create/delete | Yes | Yes |
| Batch operations | Limited | Yes (`WriteRelationships` accepts batches) |
| Read existing tuples | Yes | Yes (`ReadRelationships` with filters) |
| Schema validation | Delegated to SpiceDB | SpiceDB validates natively |
| CDC pipeline integration | Yes (SaaS) / No (on-prem) | N/A |
| Additional write-side logic | None currently | N/A |

On-prem, the Relations API adds no value for admin operations. Direct SpiceDB access provides:

1. **Batch writes** — Create multiple tuples in a single `WriteRelationships` call (workspace + bindings + resource assignments).
2. **Read capabilities** — `ReadRelationships` with filters enables admin UIs to show "who has access to what".
3. **Reduced dependencies** — One less service to deploy and maintain for write operations.
4. **Full SpiceDB flexibility** — Multiple `t_workspace` tuples per resource without any middleware constraint.

The Inventory API remains in the stack because `KesselAccessProvider` depends on it for `StreamedListObjects` and `Check`.

---

## SaaS Compatibility Analysis

| Aspect | SaaS | On-Prem | Compatible? |
|---|---|---|---|
| `KesselAccessProvider` code | Unchanged | Unchanged | **Yes** |
| `StreamedListObjects` / `Check` | Via Inventory API | Via Inventory API | **Yes** |
| `resource_reporter.py` | `on_resource_created` writes primary tuple | Same — always uses `org_id` from metrics operator | **Yes** — identical upsert behavior |
| Workspace topology | Single org-level workspace (RBAC v2 manages hierarchy) | Team workspace hierarchy (admin tooling manages) | **Compatible** — Koku is unaware of topology |
| Multiple `t_workspace` per resource | Not used (CDC creates one) | Used for cross-team sharing | **SpiceDB-compatible** — Inventory API unaffected (reads, not writes) |
| ZED schema | Canonical `rbac-config` | Same canonical schema + resource definitions ([FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)) | **Yes** — no new definitions or relations |
| Role/group management | RBAC v2 API | Admin tooling / Keycloak sync → SpiceDB | **Compatible** — different management plane, same SpiceDB model |

**Key insight**: The divergence is entirely in the **tuple management plane** (how tuples are created and by whom), not in the **authorization evaluation plane** (how permissions are checked). Koku's application code is identical in both environments.

---

## Alternatives Considered

### Alternative 1: Single Workspace (No Restriction)

All resources in the org workspace, all users bound there.

- **Rejected because**: No per-team access control. Every user sees every resource. Does not meet customer requirements.

### Alternative 2: Sub-Workspace Reassignment Only

Move resources from org workspace to sub-workspaces. No multiple `t_workspace` tuples.

- **Rejected because**: Cannot share a resource across sibling workspaces without workspace proliferation (need a dedicated workspace for every combination of teams). E.g., for 3 teams sharing different subsets: `team-A-only`, `team-B-only`, `team-C-only`, `team-A-B`, `team-A-C`, `team-B-C`, `team-A-B-C` = 7 workspaces.

### Alternative 3: Direct Group-to-Resource Relations (Schema Extension)

Add `t_viewer: rbac/principal | rbac/group#member` relation to resource definitions.

- **Rejected because**: Requires schema changes that diverge from upstream `rbac-config`. Would need Kessel team approval for a non-standard relation type. Workspace model handles the same use case without schema changes.

### Alternative 4: Resource-Level Role Bindings

Create a role_binding per resource, not per workspace.

- **Rejected because**: Role bindings are scoped to workspaces in the Kessel model, not to individual resources. Would require schema redesign.

### Alternative 5: Kessel Relations API for All Operations

Use the Relations API for both `resource_reporter` and admin operations.

- **Partially accepted**: `resource_reporter.py` continues to use the Relations API for the primary `t_workspace` tuple (SaaS-compatible path). Admin operations use SpiceDB directly for batch writes, read capabilities, and multiple `t_workspace` tuples. See [Why Direct SpiceDB](#why-direct-spicedb-for-admin-operations).

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Multiple `t_workspace` tuples diverge from Kessel Inventory API contract** | Medium | Only the admin tooling creates additional tuples. `resource_reporter.py` writes one tuple (Kessel-compatible). Inventory API reads are unaffected — `StreamedListObjects` and `Check` resolve through SpiceDB regardless of tuple count. |
| **Direct SpiceDB access bypasses future Relations API validation** | Low | On-prem controls the upgrade cycle. If the Relations API adds write-side validation in the future, the admin tooling can be updated. Currently the Relations API is a pass-through. |
| **Workspace hierarchy management complexity** | Medium | Keycloak-driven automation (Option E) handles workspace/binding lifecycle. Admin tooling provides CLI and API for manual operations. |
| **Re-ingestion writes a duplicate tuple** | Negligible | `on_resource_created` upserts with the same `org_id` every time — idempotent no-op at the SpiceDB level. |
| **Schema drift between on-prem and upstream `rbac-config`** | Medium | On-prem schema is a strict superset (adds resource definitions only, per [FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)). No modifications to existing definitions. Tracked in [zed-schema-upstream-delta.md](./zed-schema-upstream-delta.md). |

---

## Implementation Status

| Component | Status | Location |
|---|---|---|
| `KesselSyncedResource` tracking model | **Implemented** | [models.py](../../../koku/koku_rebac/models.py) |
| `on_resource_created()` — primary `t_workspace` tuple (always `org_id`) | **Implemented** | [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py) |
| `on_resource_deleted()` — cleanup primary tuple | **Implemented** | [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py) |
| Unit tests (create, delete, idempotency) | **Implemented** | [test_resource_reporter.py](../../../koku/koku_rebac/test/test_resource_reporter.py) |
| Django migration | **Implemented** | [0001_initial.py](../../../koku/koku_rebac/migrations/0001_initial.py) |
| Admin tooling (workspace CRUD, SpiceDB direct) | **Not started** | — |
| Keycloak group sync automation | **Not started** | — |
| Admin API endpoints | **Not started** | — |

---

## Open Questions

1. **Kessel team review**: Does the multiple `t_workspace` approach for cross-team sharing conflict with any planned Kessel Inventory API changes?

2. **Admin tooling delivery**: Should the admin tooling be a standalone CLI, a Koku management command, or a Helm chart hook? What's the right UX for on-prem administrators?

3. **Keycloak sync mechanism**: Push (Keycloak webhook → sync service) or pull (periodic reconciliation loop)? What Keycloak event types are available?

4. **Default workspace for new resources**: Should new resources be assigned to the org-level workspace (admin-only visibility, current implementation) or to a configurable default team workspace?

5. **Resource deletion cleanup**: When `on_resource_deleted` fires, it deletes ALL `t_workspace` tuples for the resource (including admin-managed ones) via a filter on `resource_type + resource_id + relation` without specifying a workspace subject. This is correct: if the resource's cost data has been purged from PostgreSQL, it should not remain discoverable in any workspace. No code changes needed.
