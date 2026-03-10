# ZED Schema: Upstream Delta Tracking

**Purpose**: Track all differences between the local on-prem schema (`dev/kessel/schema.zed`) and the SaaS production schema (`RedHatInsights/rbac-config`) so they can be reconciled into a single source of truth.

**Upstream repo**: [`RedHatInsights/rbac-config`](https://github.com/RedHatInsights/rbac-config)
- Schema: [`configs/prod/schemas/schema.zed`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/schemas/schema.zed)
- Roles: [`configs/prod/roles/cost-management.json`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/roles/cost-management.json)
- Permissions: [`configs/prod/permissions/cost-management.json`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/permissions/cost-management.json)

**Local schema**: [`dev/kessel/schema.zed`](../../dev/kessel/schema.zed)
**Seed command**: [`koku_rebac/management/commands/kessel_seed_roles.py`](../../koku/koku_rebac/management/commands/kessel_seed_roles.py)

**Jira**: [FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)
**Last updated**: 2026-03-02

---

## 1. Gap Summary

| # | Gap | Severity | Owner | Status |
|---|-----|----------|-------|--------|
| G-1 | [Permission wiring missing in upstream](#g-1-permission-wiring-missing-in-upstream-role_binding--tenant) | **Blocking** | Upstream PR to `rbac-config` | Open |
| G-2 | [Permission naming divergence](#g-2-permission-naming-divergence) | **Must-fix** before upstream PR | On-prem team | **Resolved** |
| G-3 | [Structural type divergence (workspace vs tenant)](#g-3-structural-type-divergence) | Design decision | On-prem team | **Resolved** |
| G-4 | [Wildcard `_all` verb permissions not in local schema](#g-4-wildcard-_all-verb-permissions-not-in-local-schema) | Medium | On-prem team | **Resolved** |
| G-5 | [Cloud permissions](#g-5-cloud-permissions) | Low (Phase 1) | Upstream PR to `rbac-config` | **In scope** — include in same PR as G-1 so Koku/SaaS are ready when SaaS onboards |

---

## 2. Detailed Gaps

### G-1: Permission Wiring Missing in Upstream (`role_binding` + `tenant`)

The SaaS production schema declares 23 `cost_management_*` permissions on `rbac/role` but does **not** propagate them through `rbac/role_binding` or `rbac/tenant`. Without this wiring, `CheckPermission()` cannot resolve cost management permissions through the authorization chain.

Our local `dev/kessel/schema.zed` has the full wiring (via `rbac/workspace`), proving the pattern works. The upstream schema needs equivalent wiring in `rbac/role_binding` and `rbac/tenant`.

**What must be added upstream** (all 23 cost_management permissions — 13 OCP + 10 cloud):

> **Note**: The upstream schema uses `t_role` as the relation name on `rbac/role_binding` (granting relation from role_binding to role). Our local on-prem `schema.zed` uses `t_granted` for the same relation. The ZED below uses the **upstream naming convention** (`t_role`) since it describes a PR to `rbac-config`.

```zed
definition rbac/role_binding {
    // ... existing permissions for other services ...

    // Cost Management OCP-scoped (13)
    permission cost_management_all_all = (subject & t_role->cost_management_all_all)
    permission cost_management_openshift_cluster_all = (subject & t_role->cost_management_openshift_cluster_all)
    permission cost_management_openshift_cluster_read = (subject & t_role->cost_management_openshift_cluster_read)
    permission cost_management_openshift_node_all = (subject & t_role->cost_management_openshift_node_all)
    permission cost_management_openshift_node_read = (subject & t_role->cost_management_openshift_node_read)
    permission cost_management_openshift_project_all = (subject & t_role->cost_management_openshift_project_all)
    permission cost_management_openshift_project_read = (subject & t_role->cost_management_openshift_project_read)
    permission cost_management_cost_model_all = (subject & t_role->cost_management_cost_model_all)
    permission cost_management_cost_model_read = (subject & t_role->cost_management_cost_model_read)
    permission cost_management_cost_model_write = (subject & t_role->cost_management_cost_model_write)
    permission cost_management_settings_all = (subject & t_role->cost_management_settings_all)
    permission cost_management_settings_read = (subject & t_role->cost_management_settings_read)
    permission cost_management_settings_write = (subject & t_role->cost_management_settings_write)
    // Cost Management cloud (10) — wire now so Koku/SaaS are ready when SaaS onboards Kessel
    permission cost_management_aws_account_all = (subject & t_role->cost_management_aws_account_all)
    permission cost_management_aws_account_read = (subject & t_role->cost_management_aws_account_read)
    permission cost_management_aws_organizational_unit_all = (subject & t_role->cost_management_aws_organizational_unit_all)
    permission cost_management_aws_organizational_unit_read = (subject & t_role->cost_management_aws_organizational_unit_read)
    permission cost_management_azure_subscription_guid_all = (subject & t_role->cost_management_azure_subscription_guid_all)
    permission cost_management_azure_subscription_guid_read = (subject & t_role->cost_management_azure_subscription_guid_read)
    permission cost_management_gcp_account_all = (subject & t_role->cost_management_gcp_account_all)
    permission cost_management_gcp_account_read = (subject & t_role->cost_management_gcp_account_read)
    permission cost_management_gcp_project_all = (subject & t_role->cost_management_gcp_project_all)
    permission cost_management_gcp_project_read = (subject & t_role->cost_management_gcp_project_read)
}

definition rbac/tenant {
    // ... existing permissions for other services ...

    // Cost Management OCP-scoped (13)
    permission cost_management_all_all = t_binding->cost_management_all_all + t_platform->cost_management_all_all
    permission cost_management_openshift_cluster_all = t_binding->cost_management_openshift_cluster_all + t_platform->cost_management_openshift_cluster_all
    permission cost_management_openshift_cluster_read = t_binding->cost_management_openshift_cluster_read + t_platform->cost_management_openshift_cluster_read
    permission cost_management_openshift_node_all = t_binding->cost_management_openshift_node_all + t_platform->cost_management_openshift_node_all
    permission cost_management_openshift_node_read = t_binding->cost_management_openshift_node_read + t_platform->cost_management_openshift_node_read
    permission cost_management_openshift_project_all = t_binding->cost_management_openshift_project_all + t_platform->cost_management_openshift_project_all
    permission cost_management_openshift_project_read = t_binding->cost_management_openshift_project_read + t_platform->cost_management_openshift_project_read
    permission cost_management_cost_model_all = t_binding->cost_management_cost_model_all + t_platform->cost_management_cost_model_all
    permission cost_management_cost_model_read = t_binding->cost_management_cost_model_read + t_platform->cost_management_cost_model_read
    permission cost_management_cost_model_write = t_binding->cost_management_cost_model_write + t_platform->cost_management_cost_model_write
    permission cost_management_settings_all = t_binding->cost_management_settings_all + t_platform->cost_management_settings_all
    permission cost_management_settings_read = t_binding->cost_management_settings_read + t_platform->cost_management_settings_read
    permission cost_management_settings_write = t_binding->cost_management_settings_write + t_platform->cost_management_settings_write
    // Cost Management cloud (10)
    permission cost_management_aws_account_all = t_binding->cost_management_aws_account_all + t_platform->cost_management_aws_account_all
    permission cost_management_aws_account_read = t_binding->cost_management_aws_account_read + t_platform->cost_management_aws_account_read
    permission cost_management_aws_organizational_unit_all = t_binding->cost_management_aws_organizational_unit_all + t_platform->cost_management_aws_organizational_unit_all
    permission cost_management_aws_organizational_unit_read = t_binding->cost_management_aws_organizational_unit_read + t_platform->cost_management_aws_organizational_unit_read
    permission cost_management_azure_subscription_guid_all = t_binding->cost_management_azure_subscription_guid_all + t_platform->cost_management_azure_subscription_guid_all
    permission cost_management_azure_subscription_guid_read = t_binding->cost_management_azure_subscription_guid_read + t_platform->cost_management_azure_subscription_guid_read
    permission cost_management_gcp_account_all = t_binding->cost_management_gcp_account_all + t_platform->cost_management_gcp_account_all
    permission cost_management_gcp_account_read = t_binding->cost_management_gcp_account_read + t_platform->cost_management_gcp_account_read
    permission cost_management_gcp_project_all = t_binding->cost_management_gcp_project_all + t_platform->cost_management_gcp_project_all
    permission cost_management_gcp_project_read = t_binding->cost_management_gcp_project_read + t_platform->cost_management_gcp_project_read
}
```

**Impact**: Without this, E2E testing against the production schema will fail. UT and IT tests (which mock gRPC) are unaffected.

---

### G-2: Permission Naming Divergence

Our local schema and seed command use **abbreviated** permission names that differ from the SaaS schema's naming convention. This must be resolved before submitting the upstream PR, and our code must be updated to match whichever convention is agreed upon.

| Resource type | SaaS upstream (`rbac-config`) | Local (`dev/kessel/schema.zed`) | Seed command (`kessel_seed_roles.py`) |
|---|---|---|---|
| AWS Account | `cost_management_aws_account_read` | `cost_management_aws_account_read` | `t_cost_management_aws_account_read` |
| AWS OU | `cost_management_aws_organizational_unit_read` | **`cost_management_aws_ou_read`** | **`t_cost_management_aws_ou_read`** |
| Azure Sub | `cost_management_azure_subscription_guid_read` | **`cost_management_azure_sub_read`** | **`t_cost_management_azure_sub_read`** |
| GCP Account | `cost_management_gcp_account_read` | `cost_management_gcp_account_read` | `t_cost_management_gcp_account_read` |
| GCP Project | `cost_management_gcp_project_read` | `cost_management_gcp_project_read` | `t_cost_management_gcp_project_read` |
| OCP Cluster | `cost_management_openshift_cluster_read` | **`cost_management_ocp_cluster_read`** | **`t_cost_management_ocp_cluster_read`** |
| OCP Node | `cost_management_openshift_node_read` | **`cost_management_ocp_node_read`** | **`t_cost_management_ocp_node_read`** |
| OCP Project | `cost_management_openshift_project_read` | **`cost_management_ocp_project_read`** | **`t_cost_management_ocp_project_read`** |
| Cost Model (read) | `cost_management_cost_model_read` | `cost_management_cost_model_read` | `t_cost_management_cost_model_read` |
| Cost Model (write) | `cost_management_cost_model_write` | `cost_management_cost_model_write` | `t_cost_management_cost_model_write` |
| Settings (read) | `cost_management_settings_read` | `cost_management_settings_read` | `t_cost_management_settings_read` |
| Settings (write) | `cost_management_settings_write` | `cost_management_settings_write` | `t_cost_management_settings_write` |

**Divergent names** (bolded above):

| Local abbreviated name | SaaS full name | Affected files |
|---|---|---|
| `ocp_cluster` | `openshift_cluster` | `schema.zed`, `kessel_seed_roles.py`, `access_provider.py` |
| `ocp_node` | `openshift_node` | `schema.zed`, `kessel_seed_roles.py`, `access_provider.py` |
| `ocp_project` | `openshift_project` | `schema.zed`, `kessel_seed_roles.py`, `access_provider.py` |
| `aws_ou` | `aws_organizational_unit` | `schema.zed`, `kessel_seed_roles.py`, `access_provider.py` |
| `azure_sub` | `azure_subscription_guid` | `schema.zed`, `kessel_seed_roles.py`, `access_provider.py` |

**Resolution (2026-02-13)**: All local names have been aligned to match upstream convention. The following files were updated:
- `dev/kessel/schema.zed` -- all permission/relation names renamed
- `koku/koku_rebac/management/commands/kessel_seed_roles.py` -- `RBAC_PERMISSION_TO_KESSEL_RELATIONS` map values renamed
- `koku/koku_rebac/access_provider.py` -- `KOKU_TO_KESSEL_TYPE_MAP` value `azure_subscription` corrected to `azure_subscription_guid`
- `koku/koku_rebac/test/test_contract.py` -- all contract test permission references renamed

---

### G-3: Structural Type Divergence

| Concept | SaaS upstream | Local on-prem (before) | Local on-prem (after) |
|---|---|---|---|
| Org-level container | `rbac/platform` → `rbac/tenant` | ~~`rbac/workspace`~~ | `rbac/tenant` |
| Role binding link | `t_binding` (on tenant) | ~~`t_user_grant`~~ | `t_binding` |
| Parent chain | `t_platform` (tenant→platform) | ~~`t_parent` (workspace→workspace)~~ | `t_platform` (tenant→tenant) |

**SaaS hierarchy**: `rbac/principal` → `rbac/role_binding` → `rbac/role` + `rbac/tenant` → `rbac/platform`

**Local hierarchy (aligned)**: `rbac/principal` → `rbac/role_binding` → `rbac/role` + `rbac/tenant`

**Resolution (2026-02-13)**: Kessel workspaces don't map well to cost management's authorization flow. The local schema has been updated to use `rbac/tenant` (matching upstream) instead of `rbac/workspace`. Relation names were also aligned: `t_user_grant` → `t_binding`, `t_parent` → `t_platform`. Contract tests updated accordingly. No production code referenced `rbac/workspace`.

---

### G-4: Wildcard `_all` Verb Permissions Not in Local Schema

The SaaS schema defines `_all` variants for every resource type (e.g., `cost_management_openshift_cluster_all`). These represent the RBAC wildcard verb `*`. Our local schema omits them and only defines `_read` and `_write`.

| SaaS upstream permission | Local schema | Notes |
|---|---|---|
| `cost_management_all_all` | Missing | Maps to RBAC `cost-management:*:*` |
| `cost_management_openshift_cluster_all` | Missing | Maps to RBAC `openshift.cluster:*` |
| `cost_management_openshift_node_all` | Missing | Maps to RBAC `openshift.node:*` |
| `cost_management_openshift_project_all` | Missing | Maps to RBAC `openshift.project:*` |
| `cost_management_cost_model_all` | Missing | Maps to RBAC `cost_model:*` |
| `cost_management_settings_all` | Missing | Maps to RBAC `settings:*` |
| `cost_management_aws_account_all` | Missing | Deferred (cloud) |
| `cost_management_aws_organizational_unit_all` | Missing | Deferred (cloud) |
| `cost_management_azure_subscription_guid_all` | Missing | Deferred (cloud) |
| `cost_management_gcp_account_all` | Missing | Deferred (cloud) |
| `cost_management_gcp_project_all` | Missing | Deferred (cloud) |

**Resolution (2026-02-13)**: All 11 `_all` verb permissions have been added to:
- `dev/kessel/schema.zed` -- `rbac/role`, `rbac/role_binding`, and `rbac/workspace` definitions
- `koku/koku_rebac/management/commands/kessel_seed_roles.py` -- `RBAC_PERMISSION_TO_KESSEL_RELATIONS` map now includes all `_all` wildcard entries

The `STANDARD_ROLES` definitions continue to list individual `_read`/`_write` permissions (matching the SaaS `cost-management.json` role spec). Custom roles using wildcard verbs (e.g., `cost-management:*:*`) will now resolve correctly through the map.

---

### G-5: Cloud Permissions

10 cloud provider permissions exist in the SaaS schema. They are now **in scope** for the same upstream PR as G-1 so that when SaaS is ready to use Kessel for cost management, Koku and the schema are already aligned.

| Permission | Verb variants | Status |
|---|---|---|
| `cost_management_aws_account` | `_all`, `_read` | **Included** in G-1 PR |
| `cost_management_aws_organizational_unit` | `_all`, `_read` | **Included** in G-1 PR |
| `cost_management_azure_subscription_guid` | `_all`, `_read` | **Included** in G-1 PR |
| `cost_management_gcp_account` | `_all`, `_read` | **Included** in G-1 PR |
| `cost_management_gcp_project` | `_all`, `_read` | **Included** in G-1 PR |

Our local `schema.zed` and seed command already define all 23 permissions. The upstream PR (G-1) now wires all 23 through `rbac/role_binding` and `rbac/tenant`.

---

## 3. Local vs Upstream Comparison Matrix

### `rbac/role` -- Permission declarations

| Permission (upstream name) | SaaS `rbac/role` | Local `rbac/role` | Match? |
|---|---|---|---|
| `cost_management_all_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_openshift_cluster_all` | Declared | Declared | Yes (G-2, G-4 resolved) |
| `cost_management_openshift_cluster_read` | Declared | Declared | Yes (G-2 resolved) |
| `cost_management_openshift_node_all` | Declared | Declared | Yes (G-2, G-4 resolved) |
| `cost_management_openshift_node_read` | Declared | Declared | Yes (G-2 resolved) |
| `cost_management_openshift_project_all` | Declared | Declared | Yes (G-2, G-4 resolved) |
| `cost_management_openshift_project_read` | Declared | Declared | Yes (G-2 resolved) |
| `cost_management_cost_model_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_cost_model_read` | Declared | Declared | Yes |
| `cost_management_cost_model_write` | Declared | Declared | Yes |
| `cost_management_settings_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_settings_read` | Declared | Declared | Yes |
| `cost_management_settings_write` | Declared | Declared | Yes |
| `cost_management_aws_account_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_aws_account_read` | Declared | Declared | Yes |
| `cost_management_aws_organizational_unit_all` | Declared | Declared | Yes (G-2, G-4 resolved) |
| `cost_management_aws_organizational_unit_read` | Declared | Declared | Yes (G-2 resolved) |
| `cost_management_azure_subscription_guid_all` | Declared | Declared | Yes (G-2, G-4 resolved) |
| `cost_management_azure_subscription_guid_read` | Declared | Declared | Yes (G-2 resolved) |
| `cost_management_gcp_account_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_gcp_account_read` | Declared | Declared | Yes |
| `cost_management_gcp_project_all` | Declared | Declared | Yes (G-4 resolved) |
| `cost_management_gcp_project_read` | Declared | Declared | Yes |

### `rbac/role_binding` -- Permission propagation

| Permission (upstream name) | SaaS `rbac/role_binding` | Local `rbac/role_binding` | Match? |
|---|---|---|---|
| All 23 cost_management permissions | **Missing** (G-1) | All 23 present | Names match; upstream wiring still needed (G-1) |

### `rbac/tenant`

| Permission (upstream name) | SaaS `rbac/tenant` | Local `rbac/tenant` | Match? |
|---|---|---|---|
| All 23 cost_management permissions | **Missing** (G-1) | All 23 present | Yes (G-3 resolved); upstream wiring still needed (G-1) |

---

## 4. Reconciliation Plan

### ~~Step 1: Align Naming (G-2)~~ -- DONE (2026-02-13)

All local permission names renamed to match upstream convention across `schema.zed`, `kessel_seed_roles.py`, `access_provider.py`, and `test_contract.py`.

### ~~Step 2: Add `_all` Verb Permissions (G-4)~~ -- DONE (2026-02-13)

All 11 `_all` verb permissions added to `schema.zed` (role, role_binding, workspace) and seed command map.

### Step 3: Submit Upstream PR (G-1) -- Blocking

PR to `rbac-config` adding permission propagation through `rbac/role_binding` and `rbac/tenant` for **all 23** cost_management permissions (13 OCP-scoped + 10 cloud). Copy-paste-ready ZED is in Section 2, G-1 above.

### Step 4: E2E Testing Against Production Schema

Once the upstream PR lands, switch E2E tests to use the production schema (fetched from `rbac-config`) instead of the local `dev/kessel/schema.zed`. The local schema remains for contract tests as a self-contained fixture.

### ~~Step 5: Wire Cloud Permissions (G-5)~~ -- In scope

Cloud permissions (10) are included in the same PR as G-1 so Koku and SaaS are ready when SaaS onboards Kessel.

---

## 5. Changelog

| Date | Change | Author |
|---|---|---|
| 2026-02-13 | Initial delta tracking document created | On-prem team |
| 2026-02-13 | G-2 resolved: renamed all abbreviated permission names to match upstream | On-prem team |
| 2026-02-13 | G-4 resolved: added all 11 `_all` wildcard verb permissions | On-prem team |
| 2026-02-13 | G-3 resolved: replaced `rbac/workspace` with `rbac/tenant`, aligned relation names | On-prem team |
| 2026-03-02 | G-5 in scope: added 10 cloud permissions to upstream PR (G-1); all 23 permissions wired in one PR so Koku/SaaS are ready when SaaS onboards Kessel | On-prem team |
