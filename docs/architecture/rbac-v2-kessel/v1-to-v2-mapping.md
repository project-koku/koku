# RBAC v1 → v2 mapping spec

**Status:** draft. Companion to the [design](README.md); execution in [`scripts/rbac_v2_lab/README.md`](../../scripts/rbac_v2_lab/README.md). Implementation: [#6477](https://github.com/project-koku/koku/pull/6477).

How a v1 authorization model (permission + resource definition + policy) becomes a v2 model (role + role binding + workspace), per tenant, with no change in effective access.

The target is the minimal shape: v2 stores grants, Cost keeps permission semantics and evaluation.

> [!warning] The one rule that drives everything
> A v2 role is a **set of permissions**, and a binding applies **the whole role** to a workspace. Therefore a v1 role can be preserved only if every permission in it has resource definitions that resolve to the *same* workspace set. Otherwise the role must be split. Most mapping bugs come from ignoring this.

## 1. Scope

In scope: permissions, roles, resource definitions, policies (group↔role), groups, principals, and the effective access map koku consumes.

Out of scope: identity/directory migration (BOP/IT stays platform-owned), the on-prem rbac-go deployment, and Cost's internal permission evaluation (which does not change).

## 2. Source model (v1)

| Construct | Shape |
|---|---|
| Permission | `app:resource:verb`, e.g. `cost-management:aws.account:*` |
| Role | name + description + list of access entries; a **named set of permissions** |
| Access entry | `{permission, resourceDefinitions[]}` |
| Resource definition (RD) | `{attributeFilter: {key, operation, value}}`, `operation ∈ {equal, in}`; koku ignores `key`; empty list = `*` |
| Policy | binds a role to a group or principal (no resource scope) |
| Effective access | union over all roles reachable from the user's groups + direct policies |

koku flattens ACLs (`koku/rbac.py:_process_acls`) into:

```
{resource_type: [{operation, resources[]}, ...]}
```

then into `user.access`:

```
{"aws.account": {"read": [ids]}, "cost_model": {"read": [ids], "write": [ids]}, ...}
```

Rules that must be preserved:

- grants are additive across roles and groups;
- any `*` in a resource list collapses to `["*"]`;
- `write` implies `read`;
- `openshift.node` / `openshift.project` are synthesized from cluster access, not granted directly;
- `ENHANCED_ORG_ADMIN` + `user.admin` bypasses everything.

The catalog (11 permissions, verified 2026-11-22):

| Permission | Verbs |
|---|---|
| `cost-management:*:*` | all |
| `cost-management:aws.account:*` | all |
| `cost-management:aws.organizational_unit:*` | all |
| `cost-management:azure.subscription_guid:*` | all |
| `cost-management:gcp.account:*` | all |
| `cost-management:gcp.project:*` | all |
| `cost-management:openshift.cluster:*` | all |
| `cost-management:cost_model:*` | read + write |
| `cost-management:cost_model:read` | read |
| `cost-management:settings:*` | read + write |
| `cost-management:settings:read` | read |

For report resource types read is the only operation, so `*` ≡ `read`.

## 3. Target model (v2)

| Construct | Shape |
|---|---|
| Role | name + description + permission list `{application, resource_type, operation}` |
| Role binding | `(subject, role, resource)` where resource = `{"type": "workspace", "id": <uuid>}` |
| Workspace | UUID + name + parent; the only scope unit |
| Subject | group UUID or user UUID; effective-grant queries resolve group membership |
| Effective access | union over bindings for the subject, each contributing the role's permissions within that workspace |

Kessel resolves `resource#permission@principal` through `workspace#binding → role_binding → role → permission`. Cost does not depend on that path: it reads bindings and evaluates locally.

Gates: the tenant must be opted in (`PATCH /api/rbac/v1/tenant/opt-in/ {"v2_opted_in": true}`) before v2 writes; the v1 `/access/` endpoint then returns 400 for apps outside `V2_MIGRATION_APP_EXCLUDE_LIST`.

## 4. Construct mapping

| v1 | v2 | Rule |
|---|---|---|
| Permission string | same string | identity mapping; `*` on report types = read |
| Role | Role | preserve name/description **only if** all its permissions share one workspace set (see §5); else split |
| Access entry | Role ↔ permission | one entry = one permission on the role |
| Resource definition (`in`, N ids) | N bindings, one per workspace | each id gets (or reuses) a workspace; bind role there |
| Resource definition (`equal`, 1 id) | 1 binding | same as `in` with N=1 |
| Empty RD (`*`) | binding on the tenant's `default` workspace | only valid if **every** object of that type lives under `default` (flat model) |
| Policy (group, role) | bindings `(group, role, workspace)` | one per workspace resolved from the role's RDs |
| Group | Group | same name; members via BOP/IT |
| Principal | Principal | resolved by `user_id`; Cost stores none |
| `admin_default` / org admin | tenant bootstrap system bindings | keep the `is_org_admin` fast path until verified |
| `openshift.node` / `openshift.project` | none | still synthesized from cluster access in koku |
| `cost_model` / `settings` RDs | workspace bindings **or** local | decision: cost models are Cost-owned; see §8 |

## 5. Role preservation rule (the important one)

Let `W(role)` be the set of workspaces derived from a role's RDs across all its permissions.

```
preserve the v1 role  ⟺  ∀ permission p in role: W(p) is identical  ∧  all permissions are scope-compatible
split the v1 role     ⟺  otherwise
```

Why: binding a role to workspace `w` grants **every** permission in the role on `w`. If `aws.account:*` points at `ws:123456789012` and `openshift.cluster:*` at `ws:abc-123`, preserving the role and binding it to both workspaces grants AWS access on the cluster workspace and vice versa — an over-grant.

Examples:

| v1 role | Verdict |
|---|---|
| `Cost OpenShift Viewer` = {`openshift.cluster:*` → [c1, c2]} | preserve; 2 bindings |
| `Cost Administrator` = {`*:*` → `*`} | preserve; 1 binding on `default` |
| `Mixed` = {`aws.account:*` → [a1], `openshift.cluster:*` → [c1]} | **split** into two v2 roles (one per resource type) |
| `Mixed*` = {`aws.account:*` → `*`, `openshift.cluster:*` → [c1]} | **split**: `*` maps to `default`, which would cover `ws:c1` too |

When splitting, name deterministically so migration is idempotent:

```
<v1 role name> · <resource_type> · <verb>        e.g. "Mixed · aws.account · *"
```

(Length limits and per-tenant uniqueness apply; truncate with a stable hash suffix.)

## 6. Workspace derivation

| Object | Workspace |
|---|---|
| provider/source (`sources` v1 RD is a wildcard app) | `ws:<source_uid>` |
| AWS account | `ws:aws:<usage_account_id>` |
| AWS organizational unit | `ws:aws-ou:<org_unit_id>` |
| Azure subscription | `ws:azure:<subscription_guid>` |
| GCP account / project | `ws:gcp:<account>` / `ws:gcp-project:<project>` |
| OCP cluster | `ws:ocp:<cluster_id>` |
| OCP node / project | not created; inherited |
| cost model | `ws:cost-model:<uuid>` (if migrated) |
| `*` (all of a type) | `default` |

Placement: all child workspaces under `default`. A binding on `default` therefore acts as "all current and future objects", which is what a v1 `*` RD means — but it also covers every other type, which is exactly why §5 forbids mixing `*` with specific RDs in one role.

Idempotency: `ws:<type>:<id>` is looked up by (org, type, id); create only if missing. Keep the mapping in Cost's own table (`org_id, resource_type, resource_id, workspace_id`).

## 7. Effective-access reconstruction (v2 → koku)

```
bindings = GET /v2/role-bindings/?granted_subject_type=principal
                           &granted_subject.principal.user_id=<id>
                           &exclude_sources=none
                           &fields=role(id,name),resource(id,name)
for each binding:
    for each permission in GET /v2/roles/<role_id>/ (cached):
        res_type, verb = permission.resource_type, permission.operation
        ops = RESOURCE_TYPES[res_type]            # read for report types
        if verb == "*":            add to all ops
        elif verb in WRITE_VERBS:  add to write and read
        elif verb == "read":       add to read
        append binding.resource.name (or mapped id) to each targeted list
collapse "*", dedupe
```

Transformations that must match v1 exactly:

- `*` in a list collapses to `["*"]`;
- `write` implies `read`;
- unknown resource types (platform roles) are ignored, never partially applied;
- node/project remain synthesized;
- org admin remains a fast path.

Verification: for a sample of users, compare the v1 `/access`-derived map with the reconstructed map; they must be equal as sets, per resource type and operation.

## 8. Cost models and settings

Two viable mappings; pick one before the first tenant migrates:

**A. Migrate to workspaces** — `cost_model:read|write` bindings on `ws:cost-model:<uuid>`. Uniform with reports, but requires a workspace per cost model and lifecycle handling (create on cost-model create, move/delete with it).

**B. Keep local** — Cost keeps the v1 RD list of cost-model UUIDs outside v2. Simpler, but reintroduces a v1-shaped grant and a special case in evaluation.

Recommendation: **A**, because a cost model is already a Cost object and KSL-75 places resources in workspaces; doing B means two authorization paths for one app.

## 9. Edge cases

| Case | Handling |
|---|---|
| RD `operation` not `equal`/`in` (e.g. `contains`) | koku ignores it → the entry grants nothing. **Fail the migration** for that role and report it; never silently drop |
| `attributeFilter.key` mismatch | ignored by koku; ignore in migration too |
| RD value contains commas inside an `in` string | v1 splits on `,`; replicate exactly, and reject ambiguous values |
| RD id no longer exists | skip, log, and list in the migration report (do not create an empty binding) |
| Duplicate ids | dedupe before creating bindings |
| Role with no permissions | skip (v1 grants nothing) |
| Role name collision after splitting | stable hash suffix |
| Multiple groups with the same role | one binding per (group, workspace) |
| User with direct policy + group policy | bindings add; v1 adds too |
| `*` RD on a role that also has specific RDs | split (§5) |
| Role carrying `cost-management:*:*` | map to `default`; keep `is_org_admin` fast path for admins |
| Deleted cost model / source | remove its workspace binding; a stale workspace grants nothing if nothing is in it |
| v1 role with `platform_default` | platform defaults are tenant-bootstrapped in v2; do not re-create per tenant |

## 10. Per-tenant procedure

```
1. inventory    read v1 roles/policies for the org, build the conversion plan (§4, §5)
2. workspaces   create ws:<type>:<id> for every referenced id; record mapping
3. roles        create/split v2 roles; record v1_role ↔ v2_role(s)
4. bindings     PUT /role-bindings/by-subject/ per (subject, workspace, role set)
5. verify       shadow-compare v1 access vs v2 reconstruction for a sample of users
6. opt-in       PATCH /v1/tenant/opt-in/ {"v2_opted_in": true}   ← v1 writes stop
7. flag         enable koku's rbac_v2 flag for the org, bump its cache generation
```

Steps 6–7 are one change window; there is no return to v1 once the app is removed from `V2_MIGRATION_APP_EXCLUDE_LIST` (see the [design's platform asks](README.md#topics-to-discuss-with-kesselrbac)).

## 11. Acceptance tests

| # | Test | Expected |
|---|---|---|
| 1 | Single permission, RD `in` (2 ids) | 2 bindings; access lists exactly those ids |
| 2 | Single permission, empty RD | 1 binding on `default`; access `["*"]` |
| 3 | Two permissions, disjoint RDs | role split; each binding grants only its permission |
| 4 | `*` + specific RD in one role | split; no over-grant on the specific workspace |
| 5 | Group-assigned role | `granted_subject_type=principal` returns group-derived bindings |
| 6 | Direct user role + group role | union |
| 7 | Cluster-only user | cluster ids only; AWS report 403; OCP-on-AWS empty |
| 8 | Cluster + account user | both reports; OCP-on-AWS intersection |
| 9 | Org admin | wildcard without bindings |
| 10 | Platform role bindings present | ignored (resource types outside `RESOURCE_TYPES`) |
| 11 | Unknown/deleted RD id | skipped and reported, no empty binding |
| 12 | v1 role with `write` | `write` and `read` both populated |

## 12. Open decisions

- §8 A vs B (cost models as workspaces).
- Whether `settings` follows cost models or stays org-wide on `default`.
- Whether node/project RDs ever need first-class workspaces (today: no).
- Where the migration plan and mapping table live per tenant (public schema vs tenant schema).
- Whether role names must be preserved for UI continuity, or deterministic split names are acceptable.

## Links

[Design](README.md) · [`scripts/rbac_v2_lab/README.md`](../../scripts/rbac_v2_lab/README.md) · [Alternatives](alternatives.md) · KSL-75

Code: `koku/rbac.py` (`_process_acls`, `_apply_access`, `_update_access_obj`) · `api/report/queries.py` (`set_access_filters`) · `insights-rbac` `management/role_binding/{queryset,serializer}.py` · `management/role/v2_service.py` · `configs/prod/schemas/schema.zed`
