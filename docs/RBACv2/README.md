# RBAC v2 design — minimal Cost integration

**Status:** experimental; disabled by default (`RBAC_BACKEND=v1`). Draft implementation: [#6477](https://github.com/project-koku/koku/pull/6477).

The smallest SaaS migration away from RBAC v1 that still uses the platform for identity: **RBAC v2 owns users, groups, and the grant store; Cost owns the permission semantics, the objects, and the evaluation.** Kessel is a replication target, not a decision point on the Cost request path.

This design supersedes the "Cost → Kessel outbox" plan for the immediate migration. The outbox approach is not wrong, it is simply not needed for this shape; it remains the deferred resource-reporting path.

> [!tip] One sentence
> Bind groups to a small set of Cost permission-roles **on an opaque workspace ID**, keep `object → workspace_id` in Cost, and evaluate reports locally. No outbox, no tuples, no `ReportResource`, no `cost-management.ksl`.

The concrete v1 → v2 conversion rules (role preservation, resource definitions, edge cases, acceptance tests) are in the v1 → v2 mapping spec (follow-up).

## Constraints that force this shape

1. **Cost cannot integrate with BOP or IT Service** — a hard limitation. Users, service accounts, groups, and group membership must come from Kessel/RBAC v2. That rules out rbac-mini (rbac-go) as a SaaS authority.
2. **RBAC v1 is being decommissioned in SaaS.** A design that keeps `/api/rbac/v1/access/` is a temporary bridge, not a destination.
3. **Sources are owned by the Sources service** (`sources-api-go` or derived). Cost must not define a `source` resource type, report sources, or write source tuples.
4. **Granular rights stay with Cost** — clusters, nodes, projects, cost models, settings, rates. Only the *grant storage and subject directory* move to the platform.

## Architecture

```
                    ┌──────────────────────────────────┐
   user identity ──▶│  RBAC v2                         │
   (x-rh-identity)  │  users · groups · roles          │
                    │  bindings (group, role, wspace)  │
                    └───────────────┬──────────────────┘
                                    │ replication only
                                    ▼
                            ┌───────────────┐
                            │ Kessel        │  no Cost Check calls
                            │ (SpiceDB)     │  in this design
                            └───────────────┘
                                    ▲
                    read bindings   │   (no writes)
                    + role perms    │
                    ┌───────────────┴──────────────────┐
                    │  Cost Management (koku)          │
                    │  · permission catalog + semantics│
                    │  · object → workspace_id table   │
                    │  · report SQL access filters     │
                    │  · read/write decision           │
                    └──────────────────────────────────┘
```

## The grant model

v2 does not store `(group, permission, workspace)`. It stores `(subject, role, resource)` where a role is a named set of permissions:

```
binding : group|user  +  role  +  workspace (resource_type=workspace, resource_id=<uuid>)
role    : name + permission list
```

To get permission-level grants, use **one role per permission**:

```json
POST /api/rbac/v2/roles/
{
  "name": "cost-aws-account-read",
  "description": "Read AWS account cost data",
  "permissions": [
    {"application": "cost-management", "resource_type": "aws.account", "operation": "read"}
  ]
}
```

Cost's v1 catalog is ~11 permissions, so ~11 roles per org. The payoff: the v1→v2 migration becomes mechanical — each v1 access entry with a resource definition turns into bindings of that one role on the workspaces containing those IDs.

Verified against the seeded catalog in the lab (2026-11-22):

| Permission | Resource type | Verbs | Used for |
|---|---|---|---|
| `cost-management:*:*` | `*` | all | org-wide wildcard (admin) |
| `cost-management:aws.account:*` | `aws.account` | all | AWS account report scoping; cost-model source |
| `cost-management:aws.organizational_unit:*` | `aws.organizational_unit` | all | AWS OU-scoped access (expands down the tree) |
| `cost-management:azure.subscription_guid:*` | `azure.subscription_guid` | all | Azure subscription scoping |
| `cost-management:gcp.account:*` | `gcp.account` | all | GCP account scoping |
| `cost-management:gcp.project:*` | `gcp.project` | all | GCP project scoping |
| `cost-management:openshift.cluster:*` | `openshift.cluster` | all | OCP cluster report scoping |
| `cost-management:cost_model:*` | `cost_model` | read + write | full cost-model access |
| `cost-management:cost_model:read` | `cost_model` | read | read-only cost models / price lists |
| `cost-management:settings:*` | `settings` | read + write | settings (tags, currency, etc.) |
| `cost-management:settings:read` | `settings` | read | read-only settings |

Two details that shape role design: `read` exists only for `cost_model` and `settings` — for report resource types `*` is the only verb and **read is the only operation**, so `*` and `read` are equivalent there and no granularity is lost (koku maps `*` to read for those types; v1 roles behave the same: *Cost OpenShift Viewer* is `openshift.cluster:*`). And `openshift.node` / `openshift.project` are absent from the lab-seeded catalog although koku's `RESOURCE_TYPES` lists them: koku synthesizes them from cluster access in `_update_access_obj`, while the prod permissions file lists them too — treat their grantability as config-dependent and confirm before migrating roles that rely on them.

The alternative (3–4 fixed Cost roles: viewer / model-admin / admin) is smaller but coarser and loses the 1:1 mapping with existing v1 data.

**Workspaces are opaque IDs to Cost.** v2 still owns the rows and the tree (`parent_id`), because bindings reference existing workspaces and inheritance lives there. Minimal first cut: **flat workspaces, direct bindings only**, so Cost does no ancestry expansion.

## Worked example

One AWS account source, one OCP cluster source, two users.

```
Source A  AWS account   uid s-aws-1   usage_account_id 123456789012
Source C  OCP cluster   uid s-ocp-1   cluster_id abc-123

workspaces: default
            ├── ws-aws  ← s-aws-1
            └── ws-ocp  ← s-ocp-1
```

| Group | Role(s) | Workspace |
|---|---|---|
| `G_cost_admins` (user1) | `cost-*` read + write roles | `default` |
| `G_ocp_viewers` (user2) | `cost-*` read roles only | `ws-ocp` |

Evaluation for `GET /reports/openshift/costs/`:

1. `GET /v2/role-bindings/?granted_subject_type=user&granted_subject_id=<uuid>` → bindings (group-derived included).
2. Join role ids → `GET /v2/roles/{uuid}/` → permission strings.
3. Build `{workspace_id → {permissions}}`.
4. Filter: workspace of each cluster ∈ user's workspaces **and** `cost-management:openshift.cluster:read` present.

| Request | user1 | user2 |
|---|---|---|
| `/reports/aws/costs/` | source A | 403 — no `aws.account` permission |
| `/reports/openshift/costs/` | source C | source C |
| OCP-on-AWS | both sides | empty — account side missing |
| `PUT /cost-models/<CM_A>` | allowed | 403 |

Read/write is **not** a property of the object. It is a different permission name in the role (`…:read` vs `…:write` / `…:*`), exactly as in v1. The object's workspace only determines **scope**.

## How Kessel models roles (background)

Kessel/SpiceDB has no native `Role`. RBAC v2 models one as a resource with one relation per permission (`rbac-config/configs/prod/schemas/schema.zed`):

```zed
definition rbac/role {
    permission cost_management_cost_model_read = t_cost_management_cost_model_read
    relation   t_cost_management_cost_model_read: rbac/principal:*
    relation   t_child: rbac/role
}
definition rbac/role_binding {
    permission inventory_host_view = (subject & t_role->inventory_host_view)
    relation   t_role: rbac/role
}
definition rbac/workspace {
    permission inventory_host_view = t_binding->inventory_host_view + t_parent->inventory_host_view
    relation   t_binding: rbac/role_binding
    relation   t_parent: rbac/workspace
}
```

A check resolves `resource#view@principal` → `t_workspace` → `workspace#permission` → binding → role → permission relation.

**The gap that keeps Cost's evaluation local:** on `rbac/workspace`, the `cost_management_*` permissions appear only as `permission X = t_X` — no `t_binding->` term, no `t_parent->` term. A v2 role can *store* a Cost permission, but a workspace `Check` for it returns false. Only migrated apps (content-sources, inventory, …) have the full wiring. So Cost reads bindings and decides locally; Kessel is not asked about Cost objects.

## API surface used

| Call | Purpose | Notes |
|---|---|---|
| `GET /api/rbac/v2/role-bindings/?granted_subject_type=user&granted_subject_id=<uuid>` | effective bindings for a user | resolves group membership server-side; `exclude_sources=none\|indirect\|direct` separates inherited |
| `GET /api/rbac/v2/role-bindings/by-subject/` | bindings for a resource, grouped by subject | requires `resource_type` + `resource_id`; good for a workspace admin view |
| `GET /api/rbac/v2/roles/{uuid}/` | permission strings for a role | platform roles expand to child roles |
| `GET /api/rbac/v2/workspaces/` | workspace IDs + tree | access-filtered; always includes root/default/ungrouped fallbacks |
| `GET /api/rbac/v2/groups/`, `/groups/{uuid}/principals/` | groups and members | fully usable |
| `GET /api/rbac/v2/principals/` | principals known to RBAC | **DB-backed, not a BOP search**; filters `type`, `username`, `order_by`; fields `uuid, username, type, user_id, service_account_id, group_count` |
| `POST /api/rbac/v2/roles/`, `/role-bindings:batchCreate/` | seed roles, create bindings | Cost's role editor |
| `POST /api/rbac/v2/groups/{uuid}/principals/` | add members | validates users against BOP, service accounts against IT, backfills local principals |

The single most useful discovery: `granted_subject_type=user` is the only filter that returns **group-derived** bindings. `subject_type=user` returns direct user bindings only.

## Ownership split

| Concern | Owner |
|---|---|
| Users, service accounts, org admin | RBAC v2 / BOP + IT |
| Groups and membership | RBAC v2 (replicated as `group:<id>#member`) |
| Grant storage (subject, role, workspace) | RBAC v2 |
| Workspace rows and tree | RBAC v2 (Cost creates them, treats as opaque) |
| Permission catalog + semantics | Cost |
| `object → workspace_id` mapping | Cost |
| Report/query scoping and evaluation | Cost |
| Sources | Sources service (Cost maps them to workspaces) |

## What this deletes

- transactional outbox, relay, tombstones, reconciler
- `ReportResource` / `DeleteResource`, Inventory resource reporting from Cost
- the `source` Kessel resource type and its reporter
- `cost-management.ksl` / `add_v1_based_permission` schema work for Cost
- per-resource tuples and any Kessel call on the Cost request path
- a Cost-owned user/group directory

Sources also stop being special: a source, cluster, account, and cost model are all just objects inside a Cost-managed workspace. That dissolves the "RBAC v2 owns sources" coordination problem — the Sources service need not participate at all; Cost enforces visibility.

## Blockers and prerequisites

> [!warning] Hard blocker today
> `cost-management` is in `V2_MIGRATION_APP_EXCLUDE_LIST` by default (`deploy/rbac-clowdapp.yml`: `ansible,automation-analytics,cost-management,hybrid-committed-spend,idmsvc,ocm,ocp-advisor,policies,sources`). `RoleV2Service._validate_and_resolve_permissions` rejects permissions from excluded apps: *"Permissions from migration-excluded applications cannot be used in V2 custom roles"*. Cost permissions cannot be stored on a v2 role until the RBAC team removes `cost-management` from that parameter per environment.

Other constraints found in code:

- **One scope per role.** `_validate_and_resolve_permissions` rejects a role mixing permissions from different scopes (ALL vs concrete). One-permission-per-role is automatically safe; never mix `rbac_*` with `cost-management:*` in one role.
- **Per-org v2 opt-in.** Writes are gated on `is_v2_opted_in(tenant)` (`V2WriteRequiresWorkspacesEnabled`); the deployed image ignores `V2_EDIT_API_ENABLED` for this check. The tenant must call `PATCH /api/rbac/v1/tenant/opt-in/ {"v2_opted_in": true}`. Non-opted-in orgs stay on v1, so Cost needs dual read paths for a while.
- **Report types only have `*`, which is equivalent to `read`.** For `aws.account`, `openshift.cluster`, etc. read is the only operation, so the missing `:read` verb costs nothing: `cost-management:openshift.cluster:*` **is** the read-only grant, exactly as in v1 ("Cost OpenShift Viewer"). `read`/`write` only diverge for `cost_model` and `settings`. This becomes a real gap only if a non-read operation is ever introduced for report data.
- **Read gate.** Unscoped `role-bindings` lists fall back to a tenant-level check (`KESSEL_TENANT_AUTH_ENABLED` / org admin). Cost's S2S identity must be allowed, or every read must be workspace-scoped.
- **No v2 user search.** `GET /principals/` only lists principals already known to RBAC (no email, no names). Org-wide "find Jane by email" is still v1 `/api/rbac/v1/principals/?usernames=…&match_criteria=…`. For a role editor this is a real gap: ask RBAC for a BOP-backed `GET /v2/principals/?username=…&match_criteria=partial&include_profiles=true`.
- **Role bootstrapping.** Roles are per-org custom roles; Cost must create them at org bootstrap and keep them in sync (name changes, new permissions).
- **The v2 management API itself depends on Kessel Inventory.** `RoleV2KesselAccessPermission` always calls `CheckForUpdate(tenant, rbac_roles_read|write, principal)` with no admin bypass (`permissions/role_v2_access.py`), and the workspace/role-binding/group v2 permissions follow the same pattern. This does not put Kessel on the Cost report path — Cost still reads bindings and evaluates locally — but it means the platform must run Inventory even for "Cost-owned" grants, and a lab needs Inventory + SpiceDB before roles can be created.

## Topics to discuss with Kessel/RBAC

Gaps found while building the lab, ordered by how much they constrain us. Each one is a platform-side change or a decision we need from the RBAC/Kessel team; none of them is something Cost can fix on its own.

| # | Topic | Ask | Why it blocks us |
|---|---|---|---|
| 1 | Tenant opt-in is irreversible | A supported downgrade path, or a documented invariant + recovery | No per-tenant rollback; a bad batch needs a database restore |
| 2 | `V2_MIGRATION_APP_EXCLUDE_LIST` is two switches in one | Decouple "v2 role allowed" from "v1 access allowed", or add a transition state | No rollback window during per-app migration |
| 3 | v1 `/access` fails hard for v2 orgs | Machine-readable error code; v2-backed v1 access during transition | koku cannot fall back safely without string matching |
| 4 | Service-to-service binding reads | Documented S2S/PSK path with org scope | Cost must use an admin identity and filter by `user_id` |
| 5 | `source` resource type ownership | Decide: Kessel resource, or workspace-level contract | Decides whether Cost ever calls `Check(source, …)` |
| 6 | Opt-in/bootstrap readiness | Readiness signal or documented retry semantics | 403 is ambiguous: not-ready vs denied |
| 7 | `fields` grammar | Document `role(name),resource(name)`; consider dotted paths | Easy to get wrong; already caused a bug |
| 8 | Report types have `*` only (≡ read) | Confirm and document; revisit only if a non-read op appears | None — `*` is already the read-only grant for reports |

### 1. Tenant opt-in is irreversible — please make it reversible

Once `TenantMapping.v2_opted_in_at` / `v2_write_activated_at` is set, the state cannot be cleared: the opt-in API accepts only `true`, `assert_v1_write_allowed` permanently rejects v1 writes, and v1 `/access` returns 400 for v2 orgs on apps outside the exclude list. In practice a per-tenant migration has **no rollback**: a bad batch means restoring that org's RBAC database snapshot.

**Ask:** a sanctioned downgrade path — an admin-only internal endpoint or documented runbook that fences v2 writes, drains, clears the activation, and restores v1 write behaviour for that tenant; or a bounded grace window in which opt-in can be reverted. If irreversibility is a deliberate invariant, state it explicitly and publish the recovery procedure.

**Why:** our rollout is one koku tenant at a time, behind an Unleash flag. Without a downgrade, the flag is one-way and every bad tenant becomes a restore.

### 2. `V2_MIGRATION_APP_EXCLUDE_LIST` is two switches in one

The same list (a) blocks those applications' permissions from **v2 custom roles** and (b) permits v1 `/access` for them on **v2 orgs**. Removing `cost-management` is therefore simultaneously the enabler for v2 Cost roles and the moment v1 `/access` starts returning 400 — which removes the rollback window exactly when migration begins.

**Ask:** decouple the two behaviours (separate flags), or support an explicit transition state where an app is "v2-capable, v1 access still served" until a cutover flag is flipped. At minimum, document the coupling and the required ordering.

### 3. Machine-readable rejection on v1 `/access` for v2 orgs

Observed: `400 {"detail":"V2 orgs may only query applications in the allowed list. Disallowed: cost-management"}`. The prose is the only signal.

**Ask:** a stable error code (e.g. `v2_org_app_not_allowed`) so koku can implement a safety net — if Unleash is unavailable at pod start, detect the state from RBAC and switch that org to v2 — without matching on English text.

### 4. Service-to-service reads of role bindings

Unscoped `GET /role-bindings/` is admin-gated when `KESSEL_TENANT_AUTH_ENABLED=False`, so Cost must read with an admin identity and filter by the target `user_id`. That is workable but not a documented contract.

**Ask:** a documented S2S/PSK or client-credentials path with org scope, confirmation that `granted_subject_type=principal` is supported for service callers, and rate/latency guidance (we cache per role and per user).

### 5. Ownership of a `source` resource type

No `source` type exists in Inventory today. If Sources is to own per-source authorization, someone must define the type, its reporter, and its relations/permissions.

**Ask:** decide whether `source` becomes a Kessel resource (and who reports it), or whether workspace-level authorization is the contract for the foreseeable future. This decides whether Cost ever calls `Check(source, …)` or only uses the local workspace mapping.

### 6. Readiness contract for opt-in and bootstrap

In the lab, v2 endpoints returned 403 until the tenant bootstrap tuples replicated into Kessel (~0.8 s locally; unbounded in production). The 403 is indistinguishable from a genuine denial.

**Ask:** a readiness signal (bootstrap status endpoint or condition) or documented retry semantics, so koku and the UI can say "not ready yet" instead of "forbidden".

### 7. `fields` grammar

`fields=role(name),resource(name)` works; dotted paths (`role.name`) are rejected. **Ask:** document the grammar and consider accepting dotted names for consistency.

### 8. Report types have `*` only — which is the same as `read`

The seeded catalog has `aws.account:*`, `openshift.cluster:*`, `gcp.*:*`, `azure.*:*`, and `read` only for `cost_model` and `settings`. This is not a granularity gap: for report data the **only operation is read**, so `*` (all operations) and `read` are the same grant. `cost-management:openshift.cluster:*` therefore *is* the read-only role — exactly what v1's *Cost OpenShift Viewer* uses, and what koku maps to `read`.

**Ask:** confirm the invariant and write it down ("report resource types expose only read; `*` is their read grant"), so it is not mistaken for a missing verb. Revisit only if a non-read operation is ever added for report data (export, sharing, annotations, …); at that point the catalog needs real verbs and the v1↔v2 mapping of `*` becomes ambiguous.

These map to the evidence in `management/tenant_mapping/v2_activation.py` (`is_v2_write_activated`, `assert_v1_write_allowed`), `management/permissions/v2_edit_api_access.py` (`V2WriteRequiresWorkspacesEnabled`), `management/access/view.py` (`validate_v2_application_param`, `rbac_v1_access_v2_org_total`), `management/role/v2_service.py` (exclude-list rejection), and `configs/prod/schemas/schema.zed` (the missing `t_binding->` wiring).

## Notes carried over

- **Regions are not an authorization scope.** No `aws.region` resource type or permission; region is a report filter (`filter[region]`) and group-by only. "Across regions" is automatic once the account is allowed. There is no way to grant `us-east-1` only.
- **OCP-on-AWS is an intersection.** v1 applies `cluster IN (…) AND account IN (…)` (`api/report/queries.py:493-499`). Kessel will not AND two workspace bindings for you, so Cost must keep that rule locally.
- **Empty resource definitions mean `*`.** v1 grants collapse to wildcard (`koku/rbac.py:_apply_access`); the v2 migration must preserve that.
- On-prem is unaffected: rbac-go remains the v1 authority there.

## Rollout

1. Feature flag: `RBAC_V2_GRANTS` (read) + `RBAC_V2_GRANTS_WRITE` (editor).
2. Build the `object → workspace_id` table; backfill every source/cluster/account/cost model to the org's default workspace.
3. Seed the per-permission Cost roles in every v2-opted org.
4. Shadow read: log the v2-derived decision next to the v1 `/access/` decision; diff for a cohort.
5. Switch enforcement per endpoint group (reports first, cost models last).
6. Keep the v1 path until the org cohort is fully on v2; then delete.

## Ephemeral test plan

A runnable version of this plan lives in [`scripts/rbac_v2_lab/README.md`](../../scripts/rbac_v2_lab/README.md) (Kessel compose stack, seed for the worked example, access-map printer).

`./scripts/ephemeral/deploy-ephemeral.sh` deploys `host-inventory kessel rbac` from `insights-stage` (v2 enabled, Kafka on, SpiceDB quantization 2.5s). Two adjustments:

```bash
-p rbac/BYPASS_BOP_VERIFICATION=True      # no BOP/IT in the namespace
# and clear cost-management from V2_MIGRATION_APP_EXCLUDE_LIST
```

Sequence: create workspaces → groups → members → per-permission roles → bindings, then verify:

1. `GET /v2/role-bindings/?granted_subject_type=user&granted_subject_id=<uuid>` returns group-derived rows.
2. `GET /v2/workspaces/` is access-filtered and includes default/root fallbacks.
3. `GET /v2/roles/{uuid}/` returns the expected permission strings.
4. `POST /v2/roles/` with a `cost-management` permission **succeeds** once the exclude list is cleared (today: rejected).
5. `POST /v2/roles/` mixing `rbac_*` and `cost-management_*` fails (scope rule).
6. Inventory `CheckForUpdate(workspace, "cost_management_cost_model_read", user)` returns **false** even with a binding, while `inventory_host_view` returns true — the schema-gap experiment.

### Local alternative: full stack with Docker Compose

Kessel's own docs have a one-command stack — [Run locally with Docker Compose](https://project-kessel.github.io/docs/building-with-kessel/how-to/run-with-docker/):

```bash
git clone https://github.com/project-kessel/inventory-api.git
cd inventory-api
make kessel-up      # needs podman/docker with the compose plugin, plus yq and curl
make kessel-down    # stops containers, keeps volumes
```

It starts Inventory API, Relations API, SpiceDB, **RBAC**, Kafka, Kafka Connect, and the Inventory Consumer, and bootstraps a tenant through RBAC v2 — so the v2 endpoints in this design are live without bonfire. Ports to point Cost at:

| Port | Service |
|---|---|
| 9080 | RBAC (HTTP) |
| 8081 / 9081 | Inventory API (HTTP / gRPC) |
| 9000 | Relations API (gRPC) |
| 50051 | SpiceDB (gRPC) |
| 9092 | Kafka |

Caveats for our checks: there is no BOP/IT behind it (group-member and principal flows need the bypass setting in the compose env, same as ephemeral); Kafka Connect is running but a custom outbox connector must be registered by hand; and `make kessel-up` downloads `schema.zed` and the RBAC roles from the **stage** `rbac-config` on every start, so the `cost-management` placeholders — and the `V2_MIGRATION_APP_EXCLUDE_LIST` behaviour — reflect stage, not a local patch. With `SCHEMA_ZED_FILE` / `RBAC_CONFIG_FILE` you can swap in local copies when testing a schema change. `make kessel-compose-integration-test` (needs `kcat`, `grpcurl`, `jq`) exercises the full RBAC v2 → Kafka → Inventory → Relations path and is a good smoke test before scripting our six checks.

## Open questions

- Do we need independent per-permission grants, or are 3–4 Cost roles enough? (Decides 11 roles vs 4.)
- Flat workspaces or a tree per account/cluster? Flat avoids ancestry logic in Cost; a tree helps "all AWS accounts" groups.
- Who creates workspaces — Cost at org bootstrap, or the RBAC UI? And who deletes them?
- Does the Sources service ever need to answer "can user see source X" itself? If yes, revisit the shared model; if no, Cost stays the only enforcer.
- S2S identity/scope for authoritative binding reads — confirm with RBAC.
- Exit path if v2 changes shape again: is the mapping table + local evaluation portable to a Kessel `Check` later? (Yes, if workspaces stay the unit.)

## References

Implementation in this repository:

- `koku/koku/rbac.py` — `RbacV2Service`, `get_rbac_service`, permission mapping
- `koku/koku/middleware.py` — backend selection
- `koku/koku/settings.py` — `RBAC_BACKEND`
- `koku/koku/test_rbac.py` — unit tests
- [`scripts/rbac_v2_lab/README.md`](../../scripts/rbac_v2_lab/README.md) — runnable lab

RBAC and Kessel code:

- `insights-rbac` v2 routes: `rbac/management/v2_urls.py`
- binding query semantics: `rbac/management/role_binding/queryset.py` (`for_granted_subject`), `view.py`, `serializer.py`
- role permission validation: `rbac/management/role/v2_service.py:109-153`
- permission shape: `rbac/management/permission/model.py` (`PermissionValue`)
- principals: `rbac/management/principal/v2_view.py`, `v2_serializer.py`
- workspace access filter: `rbac/management/workspace/filters.py`, `permissions/workspace_inventory_access.py`
- Kessel schema: [`rbac-config/configs/prod/schemas/schema.zed`](https://github.com/project-kessel/rbac-config/blob/master/configs/prod/schemas/schema.zed)
- v1 permission catalog: `configs/prod/permissions/cost-management.json`
- koku v1 evaluation: `koku/rbac.py`, `api/report/queries.py`, `api/report/aws/openshift/provider_map.py`
- sources ownership: [`sources-api-go`](https://github.com/RedHatInsights/sources-api-go) (`rbac/rbac.go` = `sources:*:*` only, no Kessel code)
