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
- [Integration as First-Class Kessel Resource](#integration-as-first-class-kessel-resource)
  - [Computed Permissions and Structural Relationships](#computed-permissions-and-structural-relationships)
  - [Authorization Cascade Example](#authorization-cascade-example)
  - [Kessel Gap Inventory](#kessel-gap-inventory)
- [PRD12 Requirements Coverage](#prd12-requirements-coverage)
  - [Current Permissions — Full Coverage](#current-permissions--full-coverage)
  - [Intersection](#intersection)
  - [Inheritance](#inheritance)
  - [Scope and Relationships (Multi-Group Membership)](#scope-and-relationships-multi-group-membership)
  - [Future Expansion — Pre-Provisioned Schema](#future-expansion--pre-provisioned-schema)
  - [Future Expansion — Split Metering/Cost/Recommendations](#future-expansion--split-meteringcostrecommendations)
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
| **ZED schema must be a superset of upstream `rbac-config`** | Existing definitions (`rbac/role`, `rbac/workspace`, etc.) are not modified. On-prem adds the `cost_management/integration` type and structural relations (`has_cluster`, `has_project`) to enable computed permissions. |
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

| `integration #t_workspace → workspace:org123` | `resource_reporter.py` | Relations API | Source creation (via `ProviderBuilder`) | Yes |
| `integration #has_cluster → openshift_cluster` | `resource_reporter.py` | Relations API | Source creation (via `ProviderBuilder`) | On-prem only (no-op when backend != rebac) |
| `openshift_cluster #has_project → openshift_project` | `resource_reporter.py` | Relations API | Data ingestion (cluster info population) | On-prem only (no-op when backend != rebac) |

`resource_reporter.py` manages the primary org-level `t_workspace` tuples and structural relationship tuples (`has_cluster`, `has_project`). All workspace hierarchy, role bindings, and group management tuples are managed by the on-prem admin plane.

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

## Integration as First-Class Kessel Resource

### Why This Type Exists

The `cost_management/integration` resource type is a **Koku-API-specific construct** that does not exist in the upstream Kessel or KSL schema. It was created to solve a visibility problem unique to Koku's data model:

Koku exposes a `/api/cost-management/v1/sources/` endpoint (the "Integrations" page in the UI) that lists configured data sources. This endpoint is **independent** from the cost report endpoints — it queries the `Sources` Django model, not the cost data tables. Without a dedicated Kessel resource backing it, the sources endpoint had no way to determine per-user source visibility:

- **Before**: The endpoint used `SettingsAccessPermission`, a blunt workspace-level capability check that grants all-or-nothing access to all sources. This made per-team source filtering impossible.
- **After**: Each source is registered as a `cost_management/integration` resource in Kessel. The sources endpoint calls `StreamedListObjects("integration")` to get the list of source UUIDs the user can see, then filters the queryset by `source_uuid__in=...`.

**The integration resource is purely a computed visibility resource.** No role bindings are ever created on it. Its `read` permission is entirely derived from the structural containment chain (`has_cluster → has_project → t_workspace`). Admin never grants access to an integration directly — they grant access to namespaces or clusters, and SpiceDB computes integration visibility automatically.

This is a new construct that must be documented as a Kessel gap: the upstream schema has no concept of application-specific "container" resources whose visibility is computed from child resource access. If Kessel adopts a similar pattern, the on-prem integration type could converge with the upstream schema.

### Why Not Business Logic Instead?

An alternative was considered: skip the integration resource type entirely and compute source visibility in Koku's business logic by joining the Sources table against the user's cluster/account access lists (the "Option A" approach). For OCP-only, this produces the same result with less schema machinery.

However, Koku supports multiple provider types — AWS (accounts, organizational units), Azure (subscription GUIDs), GCP (accounts, projects), and OCP (clusters). Each has different resource types and different join logic. Without the integration type, the sources endpoint would need type-specific filtering for every provider:

```python
# Without integration type — grows with each provider type
ocp_sources = Sources.filter(source_type="OCP", koku_uuid__in=cluster_access)
aws_sources = Sources.filter(source_type="AWS", koku_uuid__in=aws_account_access)
azure_sources = Sources.filter(source_type="Azure", koku_uuid__in=azure_sub_access)
# ... and so on for every new provider type
```

With the integration type, the sources endpoint is always one generic query regardless of provider type:

```python
# With integration type — provider-agnostic, never changes
integration_access = user.access["integration"]["read"]
return Sources.objects.filter(source_uuid__in=integration_access)
```

The provider-specific containment (`has_cluster`, `has_account`, `has_subscription`) lives in the SpiceDB schema, not in Koku's business logic. This keeps the sources-api code generic and ensures new provider types only require schema additions, not application code changes.

### Computed Permissions and Structural Relationships

The [ZED schema](../../../dev/kessel/schema.zed) defines cross-type structural relations that enable permission cascading:

```
cost_management/integration
    ├── has_cluster → cost_management/openshift_cluster
    │                     ├── has_project → cost_management/openshift_project
    │                     └── read permission cascades from has_project->read
    └── read permission cascades from has_cluster->read
```

This hierarchy means:
- **Project access** cascades upward to cluster visibility (via `has_project->read`)
- **Cluster visibility** cascades upward to integration visibility (via `has_cluster->read`)
- Admin only needs to grant namespace-level access; integration and cluster visibility is computed by SpiceDB

Structural tuples are written by Koku during data ingestion:

| Structural Tuple | Written by | When |
|---|---|---|
| `integration:<source_uuid>#has_cluster → openshift_cluster:<provider_uuid>` | `ProviderBuilder.create_provider_from_source` | OCP source creation |
| `openshift_cluster:<provider_uuid>#has_project → openshift_project:<name>` | `_report_ocp_resources_to_kessel` | Data ingestion (cluster info population) |

These tuples are deterministic and idempotent: the same source always produces the same structural relationships. Re-ingestion is safe because `create_structural_tuple` uses upsert mode.

### Authorization Cascade Example

**Scenario**: Admin grants user `test` access to namespace `payments`.

**Admin actions** (management plane only):
```
openshift_project:payments → t_workspace → rbac/workspace:team-a
rbac/role_binding:rb-test binds test to cost-openshift-viewer on team-a
```

**SpiceDB automatically computes** (via schema, zero admin action):
- `test` can view `openshift_project:payments` (direct workspace permission)
- `test` can view `openshift_cluster:cluster-A` (because `cluster-A#has_project → payments`)
- `test` can view `openshift_cluster:cluster-B` (because `cluster-B#has_project → payments`)
- `test` can view `integration:source-A` (because `source-A#has_cluster → cluster-A`)
- `test` can view `integration:source-B` (because `source-B#has_cluster → cluster-B`)

**Result**: User sees source-A and source-B on the integrations page; cost reports show only `payments` namespace data from both clusters.

**What test cannot see**: Other namespaces, cluster-wide costs, or integrations that don't contain the `payments` namespace.

### Kessel Gap Inventory

The following operations bypass the Kessel Inventory/Relations APIs and access SpiceDB directly. Each represents a gap that the Kessel team should address:

| Gap | Operation | Current Workaround | Proposed Kessel API |
|---|---|---|---|
| **Workspace management** | Create/delete `rbac/workspace` resources and `t_parent` relations | Direct SpiceDB `WriteRelationships` | Workspace CRUD endpoints on Inventory API |
| **Role binding management** | Bind roles to users/groups on workspaces | Direct SpiceDB `WriteRelationships` | Role binding CRUD endpoints on Inventory API |
| **Structural relationships** | Write `has_cluster`, `has_project` cross-type relations | `create_structural_tuple` via Relations API (REST POST) | `ReportResource` should support declaring structural relationships alongside metadata |
| **Schema deployment** | Deploy/update the `.zed` schema | Direct SpiceDB schema write or `SPICEDB_SCHEMA_FILE` env var | Schema management API or versioned schema registry |
| **CDC pipeline** | Auto-create `t_workspace` tuples from Inventory events | Disabled on-prem; Koku writes tuples via Relations API directly | On-prem CDC support or explicit `ReportResource` option to create tuples synchronously |
| **Computed permissions** | Cross-type permission resolution (`has_cluster->read`, `has_project->read`) | Custom schema additions to the on-prem `.zed` file | Upstream KSL schema support for structural resource relationships |
| **Application-specific computed-visibility resources** | `cost_management/integration` — a resource whose `read` permission is entirely derived from child resource access, not direct role bindings. Created because Koku's `/sources/` API is a separate endpoint that needs per-user filtering independent of cost report access. | Custom `integration` type in on-prem `.zed` schema; Koku registers integration resources and structural tuples during source creation and data ingestion | Upstream support for application-defined "container" resource types with computed visibility, or a generic mechanism for API endpoints to derive per-user resource lists from child access grants |

### Kessel API Authentication Hardening

The Relations API and Inventory API both support JWT-based authentication but ship with auth **disabled** by default. In the initial on-prem deployment, inter-service calls rely on network-level isolation (ClusterIP services, no external Routes) as the sole access control.

#### Unauthenticated Paths (before hardening)

| Caller | Target API | Protocol | Risk |
|---|---|---|---|
| Koku `resource_reporter.py` | Relations API | HTTP REST `:8000` | Any pod in the cluster can write/delete authorization tuples |
| Koku `client.py` | Inventory API | gRPC `:9000` | Any pod can perform Check/StreamedListObjects/ReportResource |
| Inventory API | Relations API | gRPC `:9000` | Internal authz calls are unauthenticated |

#### Authentication Design

When `kessel.auth.enabled=true` in the Helm chart (or `KESSEL_API_AUTH_ENABLED=true` for deploy scripts):

- **Two dedicated Keycloak service account clients** are created via the `KeycloakRealmImport` CR in `deploy-rhbk.sh`:
  - `cost-management-koku` — used by Koku pods for Relations API (HTTP) and Inventory API (gRPC) calls
  - `cost-management-inventory` — used by the Inventory API pod for its outbound Relations API (gRPC) calls
- **Relations API** enables JWT validation via `ENABLEAUTH=true` + `JWKSURL` pointing to Keycloak's JWKS endpoint
- **Inventory API** switches from `allow-unauthenticated: true` to an OIDC authenticator chain, and enables `enable-oidc-auth: true` for its outbound Relations API calls with SA credentials
- **Koku** uses a thread-safe `TokenProvider` ([`koku_rebac/kessel_auth.py`](../../../koku/koku_rebac/kessel_auth.py)) that acquires tokens via client_credentials grant and caches them until 30s before expiry
- **SpiceDB** remains secured by preshared key (unchanged)

#### Deployment

Kessel API authentication is **mandatory** — there is no unauthenticated mode. The deployment scripts enforce this:
1. `deploy-rhbk.sh` creates the Keycloak service account clients and extracts their secrets
2. `install-helm-chart.sh` copies `kessel-koku-client` to the cost-onprem namespace and `kessel-inventory-client` to the kessel namespace — **fails hard** if either secret is missing
3. `deploy-kessel.sh` configures Relations API with `ENABLEAUTH=true` and Inventory API with OIDC authentication — **fails hard** if the Inventory client secret is missing
4. Koku pods always set `KESSEL_AUTH_ENABLED=True` and mount the `kessel-koku-client` secret

---

## PRD12 Requirements Coverage

This section maps each requirement from [PRD12 COST-7292](https://docs.google.com/document/d/1kZoRADs0-wAalFDC4MkSFV8RxpXb1YER1UXNn-5EvdE/edit?tab=t.0#heading=h.4tv3gbbbc9rd) ("Kessel integration") to the current Kessel on-prem implementation, confirming full coverage of existing RBAC v1 capabilities and documenting the plan for future expansions.

### Current Permissions — Full Coverage

PRD12 requires that **no current RBAC v1 permission capability is lost**. All 10 resource-type read permissions plus cost model and settings read/write are supported:

| PRD Permission | Kessel Resource Type | In [Schema](../../../dev/kessel/schema.zed) | In [Access Provider](../../../koku/koku_rebac/access_provider.py) | One / Many / All |
|---|---|---|---|---|
| Read AWS account | `aws_account` | Yes | Yes | Wildcard via org workspace; specific via team workspace tuples |
| Read AWS organizational unit | `aws_organizational_unit` | Yes | Yes | Same |
| Read Azure subscription | `azure_subscription_guid` | Yes | Yes | Same |
| Read GCP account | `gcp_account` | Yes | Yes | Same |
| Read GCP project | `gcp_project` | Yes | Yes | Same |
| Read OpenShift cluster | `openshift_cluster` | Yes | Yes | Same |
| Read OpenShift node | `openshift_node` | Yes | Yes | Same |
| Read OpenShift project | `openshift_project` | Yes | Yes | Same |
| Read/Write cost model | `cost_model` | Yes | Yes | Same |
| Read/Write settings | `settings` | Yes | Yes | Same |

**"Automagically handled"** (PRD language for dynamic resource discovery): When a user has wildcard (`*`) access via the org-level workspace, new resources appear automatically because `resource_reporter.py` assigns them `t_workspace → org-workspace` on creation. For specific-resource access via team workspaces, new resources require explicit admin assignment — identical to RBAC v1's behavior with resource definitions.

### Intersection

PRD12 requires: *"it must be possible to say a user (group) only has permissions on namespace X when running on cluster Y on AWS account Z, excluding everything else."*

**This is handled identically to RBAC v1** — it is a Koku application-layer concern, not an authorization backend concern.

`StreamedListObjects` returns per-type access lists:
```
user.access = {
    "openshift.cluster": {"read": ["cluster-Y"]},
    "openshift.project": {"read": ["namespace-X"]},
    "aws.account":       {"read": ["account-Z"]},
}
```

Koku's views and serializers apply the intersection in SQL WHERE clauses: cost data must match the user's allowed cluster IDs AND project names AND account IDs. This logic is unchanged between RBAC v1 and Kessel — the access provider populates the same `user.access` dict regardless of backend.

**No SpiceDB-level intersection is needed.** SpiceDB grants access per type independently. The intersection semantics live in Koku's data query layer, where they have always lived.

### Inheritance

PRD12 requires: *"if you have read permissions on one cluster, you can also see all of the nodes and projects in that cluster."*

This is handled by **two complementary mechanisms**:

1. **Downward inheritance (Koku business logic, unchanged from RBAC v1)**: When a user has cluster-level access, Koku's SQL queries return all nodes and projects for that cluster. The `openshift_node` and `openshift_project` resource definitions in SpiceDB include the cluster-level permissions in their `read` computation:

```
definition cost_management/openshift_project {
    permission read = ... + t_workspace->cost_management_openshift_cluster_read + ...
}
```

This means: if a user has `openshift_cluster_read` on the resource's workspace, they can also read projects in that workspace. This is a SpiceDB-level inheritance that mirrors the RBAC v1 behavior.

2. **Upward cascade (structural relations, on-prem addition)**: Access to a project cascades upward to cluster and integration visibility via `has_project->read` and `has_cluster->read`. This is the reverse direction — it enables the sources endpoint to show integrations that contain resources the user can access.

Both directions are covered. Downward is the same as RBAC v1. Upward is a new on-prem addition.

### Scope and Relationships (Multi-Group Membership)

PRD12 explicitly states: *"Limiting one resource to one workspace is not acceptable since it would lead to the creation of artificial workspaces only for the purpose of ReBAC."*

And gives the example:
- Role R1: clusters A, B, C
- Role R2: clusters D, E, F
- Role R3: clusters C, D

**This is a core design decision** of this ADR: multiple `t_workspace` tuples per resource in SpiceDB. Cluster C gets `t_workspace → team-1` and `t_workspace → team-3`. Cluster D gets `t_workspace → team-2` and `t_workspace → team-3`. SpiceDB resolves all paths via union (`+`).

See [Cross-Team Resource Sharing](#cross-team-resource-sharing) for the full design.

### Future Expansion — Pre-Provisioned Schema

PRD12 mentions future resource types and structural relationships. The [ZED schema](../../../dev/kessel/schema.zed) pre-provisions these so they are ready when Koku onboards each provider or feature:

**OpenShift Virtualization VMs** (PRD12: *"Explicit read permission on OpenShift Virtualization VMs"*):

```
definition cost_management/openshift_vm {
    relation t_workspace: rbac/workspace
    permission read = ... (inherits from project, node, cluster, and all-level permissions)
}

definition cost_management/openshift_project {
    relation has_vm: cost_management/openshift_vm    ← VM access cascades upward
}
```

Full permission chain is wired through `rbac/role`, `rbac/role_binding`, `rbac/tenant`, and `rbac/workspace`. When Koku adds VM support, only application code (resource reporting, access provider type map) needs updating — the schema is ready.

**AWS structural containment** (integration → accounts, OUs → accounts):

```
definition cost_management/integration {
    relation has_account: cost_management/aws_account
    relation has_organizational_unit: cost_management/aws_organizational_unit
}

definition cost_management/aws_organizational_unit {
    relation has_account: cost_management/aws_account    ← account access cascades to OU visibility
}
```

**Azure structural containment** (integration → subscriptions):

```
definition cost_management/integration {
    relation has_subscription: cost_management/azure_subscription_guid
}
```

**GCP structural containment** (integration → accounts → projects):

```
definition cost_management/integration {
    relation has_gcp_account: cost_management/gcp_account
    relation has_gcp_project: cost_management/gcp_project
}

definition cost_management/gcp_account {
    relation has_project: cost_management/gcp_project    ← project access cascades to account visibility
}
```

These structural relations enable the same computed-permission cascade pattern proven with OCP: granting access to a leaf resource (e.g., a GCP project) automatically makes the parent resources (GCP account, integration) visible to that user. No code changes to Koku's application layer are needed — only `resource_reporter.py` additions to write the structural tuples during provider-specific data ingestion.

### Future Expansion — Split Metering/Cost/Recommendations

PRD12 mentions: *"it should be possible to say 'this user is able to see the cost data for a project but not the resource optimization recommendations' (or viceversa)."*

Currently, a single `read` permission on a resource type grants access to all data aspects (metering, cost, recommendations). To split these, the recommended approach is **aspect-based capability types** — orthogonal to resource access, modeled similarly to `settings`:

**Recommended design: Workspace-scoped capability resources**

```
definition cost_management/metering_capability {
    relation t_workspace: rbac/workspace
    permission read = t_workspace->cost_management_metering_capability_read + ...
}

definition cost_management/cost_capability {
    relation t_workspace: rbac/workspace
    permission read = t_workspace->cost_management_cost_capability_read + ...
}

definition cost_management/recommendations_capability {
    relation t_workspace: rbac/workspace
    permission read = t_workspace->cost_management_recommendations_capability_read + ...
}
```

**How it works**: A user's effective access is the intersection of two dimensions:

| Dimension | What it controls | How it's checked |
|---|---|---|
| **Resource access** (existing) | Which clusters/projects/accounts can the user see? | `StreamedListObjects` per resource type |
| **Aspect capability** (new) | What data types can the user see for those resources? | `StreamedListObjects("metering_capability")` etc. |

The Koku view layer checks both: *"does the user have access to this cluster?"* AND *"does the user have the metering capability?"*

**Per-workspace granularity**: Because capabilities are workspace-scoped, an admin can grant different aspect access per team:
- `team-full`: role with metering + cost + recommendations capabilities
- `team-cost-only`: role with cost capability only

A user in `team-cost-only` who has access to cluster-A (via that workspace) sees cost data but not metering or recommendations for cluster-A.

**Why this approach**:

| Alternative | Problem |
|---|---|
| New permission verbs per resource type (`read_metering`, `read_cost`, `read_recommendations`) | 3 verbs × 10+ types = 30+ new role relations. Schema explosion. |
| Application-level flags (no SpiceDB involvement) | Not Kessel-native. Cannot be managed by the admin tooling alongside resource access. |
| Capability types (recommended) | 3 new types following the `settings` pattern. Koku views already separate metering/cost/recommendations endpoints. The intersection with resource access happens naturally. |

**Implementation status**: Not yet implemented. The schema additions are minimal (3 new types + role/workspace propagation), and no existing definitions need modification. This can be added when Koku's roadmap prioritizes split data access.

### PRD12 Summary Matrix

| PRD Requirement | Status | Mechanism |
|---|---|---|
| Read AWS account (one / many / all, dynamic) | **Covered** | `aws_account` type + `StreamedListObjects` |
| Read AWS organizational unit (one / many / all, dynamic) | **Covered** | `aws_organizational_unit` type + `StreamedListObjects` |
| Read Azure subscription (one / many / all, dynamic) | **Covered** | `azure_subscription_guid` type + `StreamedListObjects` |
| Read GCP account (one / many / all, dynamic) | **Covered** | `gcp_account` type + `StreamedListObjects` |
| Read GCP project (one / many / all, dynamic) | **Covered** | `gcp_project` type + `StreamedListObjects` |
| Read OpenShift cluster (one / many / all, dynamic) | **Covered** | `openshift_cluster` type + `StreamedListObjects` |
| Read OpenShift node (one / many / all, dynamic) | **Covered** | `openshift_node` type + `StreamedListObjects` |
| Read OpenShift project (one / many / all, dynamic) | **Covered** | `openshift_project` type + `StreamedListObjects` |
| Read/Write cost models | **Covered** | `cost_model` type + `StreamedListObjects` |
| Read/Write settings | **Covered** | `settings` type + `SettingsAccessPermission` / `IsAuthenticated` |
| Intersection (namespace X on cluster Y on account Z) | **Covered** | Koku SQL layer applies per-type access list intersection (unchanged from RBAC v1) |
| Inheritance (cluster access → see nodes/projects) | **Covered** | SpiceDB schema (child types include parent-level permissions) + Koku SQL layer |
| Multi-group resource membership (one resource in multiple roles/groups) | **Covered** | Multiple `t_workspace` tuples per resource in SpiceDB |
| Dynamic add/delete of resources | **Covered** | `resource_reporter.py` creates/deletes tuples during ingestion; wildcard roles auto-include new resources |
| Workspace restriction (1:1) is unacceptable | **Addressed** | Core design decision: multiple `t_workspace` tuples, documented in ADR |
| OpenShift Virtualization VMs | **Schema ready** | `openshift_vm` type + `openshift_project#has_vm` pre-provisioned; awaiting Koku application code |
| AWS structural containment | **Schema ready** | `integration#has_account`, `aws_organizational_unit#has_account` pre-provisioned |
| Azure structural containment | **Schema ready** | `integration#has_subscription` pre-provisioned |
| GCP structural containment | **Schema ready** | `integration#has_gcp_account`, `integration#has_gcp_project`, `gcp_account#has_project` pre-provisioned |
| Split metering / cost / recommendations | **Designed** | Aspect-based capability types (see above); schema additions needed when Koku prioritizes |
| API-only vs UI-only users | **Future** | Application-layer concern (route middleware); no SpiceDB changes needed |

---

## SaaS Compatibility Analysis

| Aspect | SaaS | On-Prem | Compatible? |
|---|---|---|---|
| `KesselAccessProvider` code | Unchanged | Unchanged | **Yes** |
| `StreamedListObjects` / `Check` | Via Inventory API | Via Inventory API | **Yes** |
| `resource_reporter.py` | `on_resource_created` writes primary tuple | Same — always uses `org_id` from metrics operator | **Yes** — identical upsert behavior |
| Workspace topology | Single org-level workspace (RBAC v2 manages hierarchy) | Team workspace hierarchy (admin tooling manages) | **Compatible** — Koku is unaware of topology |
| Multiple `t_workspace` per resource | Not used (CDC creates one) | Used for cross-team sharing | **SpiceDB-compatible** — Inventory API unaffected (reads, not writes) |
| ZED schema | Canonical `rbac-config` | Canonical schema + resource definitions + `integration` type + structural relations (`has_cluster`, `has_project`) | **Compatible** — additions are on-prem only, do not modify upstream definitions |
| `integration` resource type | Not used | Sources registered as Kessel `integration` resources; visibility computed via structural relations | **Safe** — `StreamedListObjects("integration")` returns empty on SaaS (no resources registered). Sources view ONPREM-gated. |
| Structural tuples (`has_cluster`, `has_project`) | Not used | Written during source creation and data ingestion via Relations API | **Safe** — `create_structural_tuple` is a no-op when `AUTHORIZATION_BACKEND != "rebac"` |
| Role/group management | RBAC v2 API | Admin tooling / Keycloak sync → SpiceDB | **Compatible** — different management plane, same SpiceDB model |

**Key insight**: The divergence spans two layers: the **tuple management plane** (how tuples are created and by whom) and the **schema layer** (on-prem adds structural relations for computed permissions). Koku's shared application code remains generic — the sources-api changes are gated by `settings.ONPREM`, and the access provider addition (`integration` type) is a no-op on SaaS.

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
| **Schema drift between on-prem and upstream `rbac-config`** | Medium | On-prem schema is a superset: adds resource type definitions ([FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)), the `integration` type, and structural relations (`has_cluster`, `has_project`). No existing definitions are modified. Tracked in [zed-schema-upstream-delta.md](./zed-schema-upstream-delta.md). |
| **Structural relations diverge from upstream schema** | Medium | `has_cluster` and `has_project` are on-prem additions enabling computed permissions. These are documented as Kessel gaps and proposed for upstream adoption. If upstream adopts them, the on-prem schema converges. If not, the additions remain isolated to on-prem. |

---

## Implementation Status

| Component | Status | Location |
|---|---|---|
| `KesselSyncedResource` tracking model | **Implemented** | [models.py](../../../koku/koku_rebac/models.py) |
| `on_resource_created()` — primary `t_workspace` tuple (always `org_id`) | **Implemented** | [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py) |
| `on_resource_deleted()` — cleanup primary tuple | **Implemented** | [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py) |
| `create_structural_tuple()` — cross-type relations | **Implemented** | [resource_reporter.py](../../../koku/koku_rebac/resource_reporter.py) |
| `integration` resource reporting on source create | **Implemented** | [provider_builder.py](../../../koku/api/provider/provider_builder.py) |
| `integration` resource deletion on source destroy | **Implemented** | [sources/api/view.py](../../../koku/sources/api/view.py) |
| `has_project` structural tuples during ingestion | **Implemented** | [ocp_report_db_accessor.py](../../../koku/masu/database/ocp_report_db_accessor.py) |
| `integration` in access provider type map | **Implemented** | [access_provider.py](../../../koku/koku_rebac/access_provider.py) |
| `SourcesAccessPermission` (integration-based) | **Implemented** | [sources_access.py](../../../koku/api/common/permissions/sources_access.py) |
| Sources queryset filter by integration access | **Implemented** | [sources/api/view.py](../../../koku/sources/api/view.py) |
| `AccountSettings` read access for ONPREM | **Implemented** | [api/settings/views.py](../../../koku/api/settings/views.py) |
| ZED schema — `integration` type + structural relations | **Implemented** | [schema.zed](../../../dev/kessel/schema.zed) |
| Unit tests (create, delete, idempotency, structural tuples) | **Implemented** | [test_resource_reporter.py](../../../koku/koku_rebac/test/test_resource_reporter.py), [test_sources_access.py](../../../koku/api/common/permissions/test/test_sources_access.py) |
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
