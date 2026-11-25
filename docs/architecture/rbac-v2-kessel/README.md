# Cost Management integration with Kessel / RBAC v2

**Status:** Draft architecture (share-out)  
**Audience:** Project Kessel, RBAC v2, Platform IAM, Cost Management  
**Date:** 2026-11-25  
**Related:** Draft implementation exploration [#6477](https://github.com/project-koku/koku/pull/6477); v1 RBAC overview [`docs/rbac.md`](../../rbac.md)

---

## One-paragraph summary

To meet the SaaS RBAC v2 migration window without Kessel tag-based authorization (beyond the timeline) and without exploding SpiceDB with hundreds of thousands of OpenShift namespaces, Cost Management adopts a **two-tier model**: RBAC v2 / Kessel holds **users, groups, permission-roles, and opaque workspace bindings**; Cost holds **resource-to-workspace mappings** and is the **Policy Decision Point for Cost resources**. Cost does **not** call Kessel `Check` for lower-level Cost permissions, does **not** report resources via Inventory/`ReportResource`, and does **not** own Sources.

> Bind groups to a small set of Cost permission-roles **on an opaque workspace ID**, keep `object → workspace_id` (many-to-many) in Cost, and evaluate reports locally. No outbox, no Cost tuples, no `ReportResource`, no `cost-management.ksl` wiring required for this design.

---

## Document catalog

| Order | Document | Role |
|-------|----------|------|
| 1 | This README | Share-out architecture, decisions, platform asks, rollout |
| — | Companion (follow-up) | Concrete v1 → v2 mapping rules, acceptance tests |

---

## 1. Problem and constraints

| Driver | Implication |
|--------|-------------|
| Enterprise scale (many OCP namespaces, complex cloud allocations) | Modeling each namespace as a Kessel resource → hierarchy / graph proliferation |
| SpiceDB single-parent containment | Cannot natively express 1-to-many “same cluster in many team scopes” without tags |
| Tag-based auth not in the migration window | Cost must work around with local mapping |
| Cost cannot integrate with BOP / IT Service as authority | Users, SAs, groups, membership come from RBAC v2 |
| RBAC v1 decommissioned in SaaS | `/api/rbac/v1/access/` is a bridge, not the destination |
| **Sources is outside Cost’s remit** | Cost does not define a `source` Kessel type, report sources, or write source tuples |
| Granular Cost rights stay with Cost | Clusters, nodes, projects, accounts, cost models, settings, rates |

---

## 2. Architecture

```
                    ┌──────────────────────────────────┐
   user identity ──▶│  RBAC v2                         │
   (x-rh-identity)  │  users · groups · roles          │
                    │  bindings (subject, role, wspace)│
                    └───────────────┬──────────────────┘
                                    │ replication only
                                    ▼
                            ┌───────────────┐
                            │ Kessel        │  no Cost Check calls
                            │ (SpiceDB)     │  on the report path
                            └───────────────┘
                                    ▲
                    read bindings   │   (no Cost resource writes)
                    + role perms    │
                    ┌───────────────┴──────────────────┐
                    │  Cost Management (koku)          │
                    │  · permission semantics          │
                    │  · object ↔ workspace_id (N:M)   │
                    │  · report SQL access filters     │
                    │  · allow / 403 decision (PDP)    │
                    └──────────────────────────────────┘
```

### Framing (important for platform readers)

| Component | Role in this design |
|-----------|---------------------|
| **RBAC v2 / Kessel** | Authoritative **grant store and subject directory**. Stores roles and workspace bindings. Replicates into SpiceDB for platform apps that use `Check`. |
| **Cost Management** | **Policy Decision Point for Cost resources**. Reads bindings via RBAC v2 REST, joins local mappings, evaluates reports in SQL. |
| **Kessel `Check`** | **Not used** for Cost account/cluster/namespace/cost-model authorization on the request path. |

Inventory/`Check` may still gate **RBAC management APIs** (create role, binding, etc.). That is platform plumbing, not Cost report authorization.

### Why Cost does not call `Check` (schema reality)

Migrated apps wire workspace permissions as `t_binding->… + t_parent->…`. Cost permissions appear on `rbac/role` (so a v2 role can *store* them) but are **not** wired on `rbac/workspace` with `t_binding->` in current [`schema.zed`](https://github.com/project-kessel/rbac-config/blob/master/configs/prod/schemas/schema.zed). A workspace `Check` for `cost_management_*` returns false even with a valid binding.

**This design treats that as intentional for Phase 0:** we do not require Kessel to wire Cost into workspace `Check` for the migration. Optional future wiring could add Check for “has role on workspace” without moving resource scope out of Cost.

---

## 3. Ownership matrix

| Concern | Owner |
|---------|--------|
| Users, service accounts, org admin | RBAC v2 / BOP + IT |
| Groups and membership | RBAC v2 |
| Grant storage `(subject, role, workspace)` | RBAC v2 |
| Workspace rows and tree | RBAC v2 — **created/deleted only via Kessel / RBAC UI** |
| Permission catalog strings (seeded) | rbac-config |
| ~11 Cost permission-roles (definitions + bindings) | Stored in RBAC v2; Cost seeds/syncs roles as needed |
| Permission **semantics** (what a grant means for SQL) | Cost |
| Resource scope (`*` vs concrete IDs) | **Cost** mapping table |
| Report / cost-model / settings evaluation | Cost |
| Sources / Integrations | **Outside Cost** (platform Sources) |

---

## 4. Grant model

RBAC v2 stores `(subject, role, resource)` — not `(group, permission, workspace)` with embedded resource IDs:

```text
binding : group|user  +  role  +  workspace (resource_type=workspace, resource_id=<uuid>)
role    : name + permission list   // ZERO resource IDs on the role
```

### One role per Cost permission (~11)

| Permission | Used for |
|------------|----------|
| `cost-management:*:*` | Org-wide wildcard (admin) |
| `cost-management:aws.account:*` | AWS account report scoping |
| `cost-management:aws.organizational_unit:*` | AWS OU-scoped access |
| `cost-management:azure.subscription_guid:*` | Azure subscription scoping |
| `cost-management:gcp.account:*` | GCP account scoping |
| `cost-management:gcp.project:*` | GCP project scoping |
| `cost-management:openshift.cluster:*` | OCP cluster report scoping |
| `cost-management:cost_model:*` | Full cost-model access |
| `cost-management:cost_model:read` | Read-only cost models / price lists |
| `cost-management:settings:*` | Settings read + write |
| `cost-management:settings:read` | Read-only settings |

Coarse bundled roles (Viewer / Admin only) are **out of scope for Phase 0** — they lose 1:1 mapping with v1 access data.

**Two different stars:**

| Star | Where | Meaning |
|------|--------|---------|
| Permission op `:*` | On the **RBAC role** | Verb (for report types ≈ read) |
| Resource id `*` | In **Cost mapping** | All resources of that type in the workspace |

Cost manages **resource scope** (`*` vs `[account, …]`). Verbs live on the seeded roles.

---

## 5. Cost resource mapping (Tier 2)

Cost stores many-to-many links:

```text
(resource_id, resource_type, workspace_id)
```

- Same cluster / namespace / account **may appear in multiple workspaces** (Cost-side only).
- Kessel’s containment model stays 1:1 / single-parent; Cost does not push N:M into SpiceDB.
- Workspaces are **opaque UUIDs** to Cost. Cost does **not** create workspaces (RBAC UI only).
- Phase 0 workspaces are **flat for Cost evaluation** (same as today): Cost does not walk `parent_id` / ancestry for authorization.

Mapping covers top-level containers (AWS accounts, OCP clusters, GCP projects, …) and finer Cost-scoped objects (namespaces, cost models, wildcards) as needed by product — all local to Cost.

---

## 6. Evaluation rules (PDP)

Effective access requires **both**:

1. **Binding:** user (directly or via group) has the relevant Cost permission-role on workspace `W`
2. **Mapping:** Cost has mapped `*` or concrete resource IDs for that type onto `W`

| Situation | Result |
|-----------|--------|
| No bindings for the user | **403** |
| Binding on `W`, but no Cost mapping for that type on `W` | **403** |
| Binding + mapping; query returns no rows (filters/dates) | **200** with `[]` |
| Binding + mapping with concrete IDs | Allow only those resources |
| Binding + mapping with `*` | Allow all resources of that type under the tenant for that path |

### Additional invariants

- **OCP-on-cloud is an intersection.** Cost keeps local `cluster IN (…) AND account IN (…)`. Kessel will not AND two workspace bindings for Cost.
- **Regions are not an authorization scope.** No `aws.region` permission; region remains a report filter / group-by.
- **Empty v1 resource definitions migrate to `*`** in Cost mapping (preserve v1 wildcard behavior).
- **On-prem:** unchanged — rbac-go / rbac-mini remains the v1 authority; not a SaaS translation proxy.

---

## 7. Runtime and admin flows

### Admin configuration

1. **RBAC / Kessel UI:** Org admin creates groups, members, and **workspaces**; binds groups to Cost permission-roles on those workspaces.
2. **Cost UI:** Cost admin maps AWS accounts, OCP clusters, namespaces, cost models, etc. onto existing workspace UUIDs (`*` or explicit lists). Until mapping exists, bindings alone do not authorize reports.

### Runtime query

```text
[ User Request ] ──► [ Koku API ]
        │
        ▼
1. GET /api/rbac/v2/role-bindings/?granted_subject_type=user&granted_subject_id=<uuid>
   → bindings (group-derived included) + resolve roles → permissions
        │
        ▼
2. Cost joins local mappings for authorized workspace IDs
        │
        ▼
3. If binding ∧ mapping fail → 403
   Else filter SQL by mapped resources / workspaces
```

`granted_subject_type=user` is required to receive **group-derived** bindings (`subject_type=user` alone returns direct user bindings only).

---

## 8. What this design deliberately does not do

- Transactional outbox, relay, tombstones, reconciler for Cost resources  
- `ReportResource` / `DeleteResource` / Inventory resource reporting from Cost  
- A Cost-owned Kessel `source` resource type  
- `cost-management.ksl` / `add_v1_based_permission` schema work **as a migration dependency**  
- Per-resource SpiceDB tuples or Kessel `Check` on the Cost report path  
- Cost-owned user/group directory  
- Cost creating or deleting workspaces  

**Deferred (not cancelled forever):** a resource-reporting / outbox path remains a possible later evolution if product needs Kessel-visible Cost resources. It is **not** required for this Phase 0 shape.

---

## 9. SaaS vs on-premises

| Deployment | Behavior |
|------------|----------|
| **SaaS** | Cost reads RBAC v2 APIs; evaluates with local mapping tables |
| **On-prem** | rbac-go (rbac-mini) remains v1; no Kessel dependency for Cost auth |

---

## 10. Rollout, canary, and rollback

### Three control planes

| Layer | Examples | Owner |
|-------|----------|--------|
| 1. Platform / tenant v2 readiness | Workspaces experience flags (e.g. `platform.rbac.workspaces`), tenant `v2_opted_in` | RBAC / platform |
| 2. RBAC server gates | `V2_MIGRATION_APP_EXCLUDE_LIST` (includes `cost-management` today) | RBAC |
| 3. Cost enforcement | `RBAC_BACKEND` (default `v1`), `RBAC_V2_GRANTS` (read), `RBAC_V2_GRANTS_WRITE` (editor) | Cost (Unleash / settings) |

Do **not** treat a single platform workspaces flag as Cost enforcement.

### Desired lifecycle

```text
Phase A — Shadow (reversible)
  Enforce v1; also compute v2 decision; log/diff.
  Rollback = disable shadow.

Phase B — Enforce v2 with v1 safety net (reversible while v1 still serves Cost)
  Prefer v2; on v2 read failure fall back to v1.
  Requires dual-write / exclude-list window so v1 /access still works.

Phase C — Enforce v2 only
  After shadow is clean and platform dependencies are met.
```

**Desired approach:** dual-read and dual-write with Unleash rollback through the transition window. Today, tenant `v2_opted_in` / `v2_write_activated_at` is effectively **irreversible** in RBAC, and removing `cost-management` from the exclude list both enables v2 Cost roles and makes v1 `/access` return 400 for Cost — collapsing the rollback window. See platform asks below.

### Cost rollout checklist (high level)

1. Feature flags: `RBAC_V2_GRANTS` + `RBAC_V2_GRANTS_WRITE` (and `RBAC_BACKEND`).
2. Build `object ↔ workspace_id` mapping; backfill (e.g. default workspace) as product requires.
3. Seed per-permission Cost roles in v2-opted orgs.
4. Shadow read / compare vs v1.
5. Switch enforcement per endpoint group (reports first, cost models last).
6. Keep v1 path until the org cohort is fully on v2; then remove.

---

## 11. Platform asks (Kessel / RBAC)

Cost cannot fix these alone. Ordered by how much they constrain migration and rollback.

| # | Topic | Ask |
|---|--------|-----|
| 1 | Tenant opt-in irreversible | Supported downgrade path, or documented invariant + recovery runbook |
| 2 | `V2_MIGRATION_APP_EXCLUDE_LIST` is two switches | Decouple “v2 role allowed” from “v1 access still served”, or an explicit transition state |
| 3 | S2S binding reads | Documented S2S/PSK (or client-credentials) path with org scope for `GET /role-bindings/` |
| 4 | v1 `/access` rejection for v2 orgs | Machine-readable error code (not English-only `detail`) |
| 5 | Opt-in / bootstrap readiness | Readiness signal or retry semantics (403 vs not-ready) |
| 6 | `source` resource type | Confirm workspace-level / Sources-owned contract; Cost will not report `source` |
| 7 | `fields` grammar | Document `role(name),resource(name)`; consider dotted paths |
| 8 | Catalog confirmation | Confirm report-type verbs and whether `openshift.node` / `openshift.project` are grantable for migration roles |

**Not asked for Phase 0:** wiring `cost_management_*` into `rbac/workspace` `Check` — intentionally out of this design.

Hard blocker today: `cost-management` is on `V2_MIGRATION_APP_EXCLUDE_LIST` by default, so Cost permissions cannot be stored on v2 custom roles until RBAC clears that per environment.

---

## 12. API surface Cost uses (RBAC v2)

| Call | Purpose |
|------|---------|
| `GET /api/rbac/v2/role-bindings/?granted_subject_type=user&granted_subject_id=<uuid>` | Effective bindings (incl. group-derived) |
| `GET /api/rbac/v2/roles/{uuid}/` | Permission strings for a role |
| `GET /api/rbac/v2/workspaces/` | Discover opaque workspace IDs (access-filtered; includes platform defaults) |
| `GET /api/rbac/v2/groups/`, `/groups/{uuid}/principals/` | Groups / members |
| `POST /api/rbac/v2/roles/`, `/role-bindings:batchCreate/` | Seed roles / create bindings (Cost editor path) |

---

## 13. Advantages (for platform and Cost)

| Metric | If every Cost object were a Kessel resource | This design |
|--------|-----------------------------------------------|-------------|
| SpiceDB graph size | High risk (namespaces × tenants) | Minimal — workspaces, groups, role bindings |
| Resource reporting / CDC | Required | None from Cost |
| 1-to-many scoping | Needs tags / workarounds | Cost SQL / mapping table |
| Report-path dependency on Check | Yes | No |
| Migration risk | High | Canary via Cost flags + shadow; rollback depends on platform asks |

---

## 14. Open / follow-up (not blocking this draft’s shape)

| ID | Item | Notes |
|----|------|--------|
| F-1 | v1 → v2 mapping acceptance tests | Companion doc |
| F-2 | Exact Cost flag names in production Unleash | Draft names from design: `RBAC_V2_GRANTS`, `RBAC_V2_GRANTS_WRITE`, `RBAC_BACKEND` |
| F-3 | Whether Cost sources list/stats UI later filters by mapping | Product choice; **not** a Kessel `source` type (Sources remains out of scope) |
| F-4 | Optional later schema wiring for Check | Portable if workspaces remain the unit; resource scope stays in Cost |
| F-5 | Platform dual-write / downgrade feasibility | Desired; see asks 1–2 |

---

## 15. References

**Cost / koku**

- [`docs/rbac.md`](../../rbac.md) — current v1 RBAC usage in Cost  
- [`koku/koku/rbac.py`](../../../koku/koku/rbac.py) — access mapping / evaluation entry  
- [`koku/api/report/queries.py`](../../../koku/api/report/queries.py) — report scoping (incl. OCP-on-cloud intersection)  
- Draft PR: [#6477](https://github.com/project-koku/koku/pull/6477)

**Platform**

- [rbac-config `schema.zed`](https://github.com/project-kessel/rbac-config/blob/master/configs/prod/schemas/schema.zed)  
- [rbac-config `cost-management.json`](https://github.com/project-kessel/rbac-config/blob/master/configs/prod/permissions/cost-management.json)  
- [sources-api-go](https://github.com/RedHatInsights/sources-api-go) — Sources ownership (outside Cost)  
- [Kessel docs — RBAC](https://project-kessel.github.io/docs/building-with-kessel/how-to/rbac/)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-11-25 | Initial draft: merged minimal Cost integration design with two-tier share-out narrative; locked decisions from architecture review |
