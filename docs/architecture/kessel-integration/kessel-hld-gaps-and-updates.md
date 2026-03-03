# HLD Gaps and Inconsistencies (vs. Implemented Kessel Integration)

**Purpose**: Differences between the HLD in [PR #5887](https://github.com/project-koku/koku/pull/5887) (`kessel-ocp-integration.md`) and the implementation on branch `FLPATH-3294/kessel-rebac-integration`. Use this to update the HLD so it matches the built system.

**Reference implementation**: `koku_rebac` app; detailed design: [kessel-ocp-detailed-design.md](./kessel-ocp-detailed-design.md).

---

## 1. Authorization API: Check vs. StreamedListObjects + Check

| HLD says | Implementation |
|----------|----------------|
| **Phase 1**: Wildcard only via `Check(principal, permission, tenant)`. **Phase 2**: Resource-specific via `Check(principal, permission, resource_object)`. | **Single pattern**: Per-resource types use **StreamedListObjects** (Inventory API v1beta2) to get allowed resource IDs; **Check** is used only as fallback for workspace-level wildcard when StreamedListObjects returns empty. No per-resource `Check` on resource objects. |
| Authorization Adapter calls "Kessel Check API" / "CheckPermission". | `KesselAccessProvider` calls **Inventory API v1beta2** gRPC: `StreamedListObjects` for resource types, `Check` for workspace (e.g. settings) and fallback. |

**HLD update**: Replace the "Phase 1 = Check only, Phase 2 = resource Check" narrative with the **adapter pattern**: StreamedListObjects for per-resource IDs, Check for workspace-level and fallback. Add a short "Authorization flow" subsection that names Inventory API v1beta2 and the two methods. Update sequence diagrams §4 and §5 so the adapter calls StreamedListObjects (and optionally Check fallback), not only CheckPermission on a resource object.

---

## 2. Kessel APIs: Inventory API vs. Relations API

| HLD says | Implementation |
|----------|----------------|
| "CreateResource", "DeleteResource", "CreateRelation" via **Kessel Relations API**. | **Inventory API (gRPC)**: `ReportResource`, `DeleteResource` for resource metadata. **Relations API (REST)**: Used only for **t_workspace** tuple create/delete (POST/DELETE `/api/authz/v1beta1/tuples`). No CreateResource in Relations API for resources. |
| Resource sync: "Reporter->Kessel: Create cluster resource" and "CreateRelation(..., owner, ...)". | Resource creation: (1) **ReportResource** (Inventory gRPC), (2) **POST t_workspace** tuple (Relations REST). No separate "owner" relation created by Koku; authorization is via role_binding/tenant and t_workspace visibility. |

**HLD update**: In "Resource Synchronization" and sequence diagrams §3 and §6, state that resource lifecycle uses **two APIs**: (1) **Inventory API** (gRPC): ReportResource / DeleteResource; (2) **Relations API** (REST): t_workspace tuple create/delete only. Remove or reframe "CreateResource" / "CreateRelation(owner)" to match the dual-phase lifecycle. Add a note on **on-prem gap**: CDC is disabled on-prem, so Koku writes/deletes t_workspace tuples directly (see [kessel-authorization-delegation-dd.md](./kessel-authorization-delegation-dd.md) §6).

---

## 3. Package and File Paths

| HLD says | Implementation |
|----------|----------------|
| `koku/kessel/authorization_service.py`, `koku/kessel/resource_reporter.py`, "Authorization Adapter", "KesselResourceReporter". | **Package**: `koku_rebac`. **Files**: `koku/koku_rebac/access_provider.py` (KesselAccessProvider), `koku/koku_rebac/resource_reporter.py`, `koku/koku_rebac/client.py` (Inventory gRPC client), `koku/koku_rebac/workspace.py` (resolver). No `kessel` package. |

**HLD update**: Replace all `koku/kessel/` paths and "KesselAuthorizationBackend" / "KesselResourceReporter" with `koku_rebac` and `KesselAccessProvider` / resource_reporter module. Point to [kessel-ocp-detailed-design.md](./kessel-ocp-detailed-design.md) and the file map in [kessel-handover-session-2.md](./kessel-handover-session-2.md) §3.6.

---

## 4. Deployment / Environment Flag

| HLD says | Implementation |
|----------|----------------|
| PR #5887 summary and some deployment text mention **KOKU_ONPREM_DEPLOYMENT** (e.g. for Unleash). | Backend selection uses **ONPREM** env var; `ONPREM=true` forces `AUTHORIZATION_BACKEND=rebac`. No KOKU_ONPREM_DEPLOYMENT in koku_rebac. |

**HLD update**: Use **ONPREM** consistently for authorization backend selection in the Kessel/ReBAC sections. If KOKU_ONPREM_DEPLOYMENT exists elsewhere (e.g. feature flags), clarify that ONPREM is the variable that gates Kessel.

---

## 5. Error Handling: HTTP Status When Kessel Is Unavailable

| HLD says | Implementation |
|----------|----------------|
| "503 Service Unavailable" and response body `{error: "Authorization service unavailable"}`. | **HTTP 424 (Failed Dependency)** when Kessel is unavailable (KesselConnectionError), consistent with RBAC failure handling. |

**HLD update**: In §7 (Error Handling: Kessel Unavailable) and any runbooks, change 503 to **424 Failed Dependency** and align message with actual middleware behavior.

---

## 6. Phasing: Delivered in One Branch

| HLD says | Implementation |
|----------|----------------|
| **Phase 1**: Wildcard only (0–1 month). **Phase 2**: Resource-specific (2–4 months). **Phase 1.5**: Access Management API & UI. | **Phases 1 and 2** are implemented together in one branch: StreamedListObjects + Check fallback, resource reporting, dual-phase lifecycle. **Phase 1.5** (Access Management API & UI) is **not implemented**; document as future work. |

**HLD update**: State that the current implementation delivers Phase 1 and Phase 2 in a single branch (wildcard + per-resource via StreamedListObjects). Keep Phase 1.5 (Access Management API & UI) as planned future work and mark it "Not implemented" where relevant.

---

## 7. Resource Sync: Tracking Model and Lifecycle

| HLD says | Implementation |
|----------|----------------|
| Table `kessel_synced_resources` with columns e.g. `parent_cluster_id`, `discovered_at`, `last_sync_error`. | **Model**: `KesselSyncedResource` (table `kessel_synced_resource`) with `resource_type`, `resource_id`, `org_id`, `kessel_synced`, `last_synced_at`, `created_at`, `updated_at`. Unique on (resource_type, resource_id, org_id). No `parent_cluster_id` or `discovered_at`. |

**HLD update**: Replace the tracking table description with the actual `KesselSyncedResource` schema and note that hierarchy is implicit (org_id, resource_type) rather than parent_cluster_id. Optionally mention cleanup of orphaned Kessel resources when cost data expires.

---

## 8. Permission Classes and Middleware

| HLD says | Implementation |
|----------|----------------|
| Modify `openshift_access.py` permission classes to call authorization service; `has_object_permission()` for resource-specific. | Authorization is resolved in **middleware** (`IdentityHeaderMiddleware`); it populates `request.user.access` (same shape as RBAC). Permission classes and query layer are **unchanged**; they still read the access dict. No permission-class changes for Kessel-specific logic. |

**HLD update**: Describe that the Kessel path uses the same **access map** shape as RBAC; the **middleware** (with KesselAccessProvider) fills that map. Permission classes and data filtering remain unchanged. Remove or soften "Modify permission classes" for Kessel-specific code.

---

## 9. Schema and Upstream PR (G-1)

| HLD says | Implementation |
|----------|----------------|
| "3 OCP resource type definitions" missing; Phase 2 requires "Schema PR with 3 resource definitions". | Upstream gap is **wiring** cost_management_* through **rbac/role_binding** and **rbac/tenant** (all 23 permissions, including 10 cloud). Resource visibility uses Inventory API + t_workspace; no new ZED resource definitions required for the current flow. See [zed-schema-upstream-delta.md](./zed-schema-upstream-delta.md) and FLPATH-3319. |

**HLD update**: Align "Current State / Gap Analysis" with the delta doc: the blocking change is the **rbac-config** PR that wires all 23 cost_management permissions through role_binding and tenant (G-1). Reference zed-schema-upstream-delta.md and FLPATH-3319; do not imply that "3 new ZED resource type definitions" are the only or main schema change.

---

## 10. Access Management API and UI

| HLD says | Implementation |
|----------|----------------|
| Phase 1.5: "Access Management API" and "Access Management UI" (new components, REST API, React UI). | **Not implemented.** No Access Management API or UI in the branch. Role/tenant management is out of scope for current delivery. |

**HLD update**: Keep these as **planned / future work**. Clearly mark "Access Management API" and "Access Management UI" as **Phase 1.5 — not implemented** in the component overview and rollout plan.

---

## 11. Broken or Missing Doc Links

| HLD says | Implementation |
|----------|----------------|
| Links to `kessel-only-role-provisioning.md`, `kessel-ocp-implementation-guide.md`. | These files are not in the repo (not in PR #5887). They cause broken links. |

**HLD update**: Remove or replace links to non-existent docs. Point to [kessel-ocp-detailed-design.md](./kessel-ocp-detailed-design.md), [kessel-authorization-delegation-dd.md](./kessel-authorization-delegation-dd.md), and [dev/kessel/README.md](../../dev/kessel/README.md) where appropriate. For role seeding, reference the detailed design and `kessel_seed_roles` / deploy scripts.

---

## Summary: Recommended HLD Edits (Priority)

1. **Critical**: Authorization flow — StreamedListObjects + Check fallback; Inventory API v1beta2 (not only Check / Relations API).
2. **Critical**: Resource lifecycle — dual-phase: ReportResource + t_workspace (Inventory API + Relations API); no CreateResource/CreateRelation(owner) as in current diagrams.
3. **Critical**: File paths and component names — `koku_rebac`, `KesselAccessProvider`, actual file list.
4. **High**: Error handling — 424 (Failed Dependency), not 503.
5. **High**: Phasing — Phase 1+2 delivered together; Phase 1.5 (Access Mgmt API/UI) not implemented.
6. **High**: Schema gap — G-1 wiring in rbac-config (23 permissions); reference zed-schema-upstream-delta and FLPATH-3319.
7. **Medium**: ONPREM env var; middleware populates access (no permission-class changes); KesselSyncedResource model; fix/remove broken links.

---

## References

- Implementation: `koku/koku_rebac/` (access_provider.py, resource_reporter.py, client.py, workspace.py, models.py).
- Detailed design: [kessel-ocp-detailed-design.md](./kessel-ocp-detailed-design.md).
- Handover and file map: [kessel-handover-session-2.md](./kessel-handover-session-2.md).
- ZED schema delta: [zed-schema-upstream-delta.md](./zed-schema-upstream-delta.md).
- Delegation and tuple lifecycle: [kessel-authorization-delegation-dd.md](./kessel-authorization-delegation-dd.md).
