## Summary

The production ZED schema in [rbac-config](https://github.com/RedHatInsights/rbac-config) (`configs/prod/schemas/schema.zed`) defines 23 `cost_management_*` permissions on `rbac/role` but does **not** propagate them through `rbac/role_binding` or `rbac/tenant`. Without this wiring, **StreamedListObjects()** and **Check()** (Kessel Inventory API v1beta2) cannot evaluate cost management permissions through the authorization chain.

## Scope

**All 23** cost_management permissions (13 OCP-scoped + 10 cloud). Wiring cloud permissions now so Koku and SaaS are ready when SaaS onboards Kessel.

**Permissions to wire:**

*OCP (13):*
- cost_management_all_all (global wildcard)
- cost_management_openshift_cluster_all, cost_management_openshift_cluster_read
- cost_management_openshift_node_all, cost_management_openshift_node_read
- cost_management_openshift_project_all, cost_management_openshift_project_read
- cost_management_cost_model_all, cost_management_cost_model_read, cost_management_cost_model_write
- cost_management_settings_all, cost_management_settings_read, cost_management_settings_write

*Cloud (10):*
- cost_management_aws_account_all, cost_management_aws_account_read
- cost_management_aws_organizational_unit_all, cost_management_aws_organizational_unit_read
- cost_management_azure_subscription_guid_all, cost_management_azure_subscription_guid_read
- cost_management_gcp_account_all, cost_management_gcp_account_read
- cost_management_gcp_project_all, cost_management_gcp_project_read

## Changes Required

PR to [RedHatInsights/rbac-config](https://github.com/RedHatInsights/rbac-config):
- **rbac/role_binding:** Add 23 permission arrows using existing pattern `(subject & t_role->X)`
- **rbac/tenant:** Add 23 permission arrows using existing pattern `t_binding->X + t_platform->X`

Purely additive; no existing permissions modified.

Copy-paste-ready ZED blocks are in the Koku repo: `docs/architecture/kessel-integration/zed-schema-upstream-delta.md` Section 2, Gap G-1.

## Validation

- Validate locally with SpiceDB before submitting upstream PR
- Create test relationships and verify with `zed permission check`

## Blocking

Blocks E2E tests for Kessel/ReBAC integration (FLPATH-3294). Unit and integration tests (mocked gRPC) are unaffected.

---

## Gaps discovered during Koku Kessel development

While implementing Koku's Kessel support (FLPATH-3294), we documented all schema deltas between local on-prem schema and upstream rbac-config. Full tracking: **koku repo** `docs/architecture/kessel-integration/zed-schema-upstream-delta.md`.

| Gap | Description | Severity | Status |
|-----|-------------|----------|--------|
| **G-1** | Permission wiring missing in upstream (`role_binding` + `tenant`) — cost_management_* not propagated | **Blocking** | **Open** — this ticket |
| G-2 | Permission naming divergence (e.g. ocp_cluster vs openshift_cluster, aws_ou vs aws_organizational_unit) | Must-fix before upstream PR | **Resolved** (2026-02-13): local schema and code aligned to upstream naming |
| G-3 | Structural type divergence (workspace vs tenant, t_user_grant vs t_binding) | Design decision | **Resolved** (2026-02-13): local schema uses rbac/tenant, t_binding, t_platform to match upstream |
| G-4 | Wildcard `_all` verb permissions not in local schema | Medium | **Resolved** (2026-02-13): all 11 _all permissions added to local schema and seed command |
| G-5 | Cloud permissions (AWS, Azure, GCP) | Low / Phase 2 | **In scope** — include in this PR so Koku/SaaS are ready when SaaS onboards Kessel |

**Takeaway for rbac-config PR:** Wire all 23 permissions (13 OCP + 10 cloud) in one PR. G-2, G-3, G-4 were fixed on our side. Use upstream permission names (openshift_*, aws_organizational_unit, azure_subscription_guid) and the exact ZED snippets in the delta doc (Section 2, G-1) to avoid regressions.
