# Kessel/ReBAC Integration -- Handoff for Incoming Team

| Field | Value |
|---|---|
| Jira (Koku) | [FLPATH-3294](https://issues.redhat.com/browse/FLPATH-3294) |
| Jira (ros-ocp-backend) | [FLPATH-3338](https://issues.redhat.com/browse/FLPATH-3338) |
| Parent story | [FLPATH-2690](https://issues.redhat.com/browse/FLPATH-2690) |
| Author | Jordi Gil |
| Date | 2026-02-13 |
| Last updated | 2026-03-02 |

---

## 1. What Is This Project? (Start Here)

### The Product

**Cost Management for OpenShift** is a platform that collects OpenShift cluster metrics and provides resource optimization recommendations. It has three main components:

| Component | Language | Framework | Repo | Purpose |
|---|---|---|---|---|
| **Koku** | Python 3.11 | Django REST Framework | `insights-onprem/koku` | Cost data ingestion, processing, and API (AWS, Azure, GCP, OCP) |
| **ros-ocp-backend** | Go 1.23 | Echo + GORM + Ginkgo | `insights-onprem/ros-ocp-backend` | OpenShift resource optimization recommendations API |
| **ros-helm-chart** | YAML | Helm 3 | `insights-onprem/ros-helm-chart` | Deployment packaging for on-prem OCP clusters |

Both Koku and ros-ocp-backend serve API endpoints that require authorization. In SaaS, this is handled by Red Hat's **RBAC service** (an HTTP API). On-premise deployments have no RBAC service.

### The Problem

On-prem needs an authorization system. **Kessel** is Red Hat's new Relationship-Based Access Control (ReBAC) platform. This project adds Kessel support to both Koku and ros-ocp-backend so that:

- SaaS continues using RBAC (unchanged)
- On-prem uses Kessel (new)
- The same codebase supports both, selected by configuration

### What Kessel Is

- [Project Kessel](https://github.com/project-kessel) -- Red Hat's authorization platform
- Built on [SpiceDB](https://authzed.com/spicedb) (Google Zanzibar-inspired authorization database)
- Two APIs work in tandem:
  - **Inventory API** (gRPC): ReportResource / DeleteResource for resource metadata; Check / StreamedListObjects for authorization
  - **Relations API** (REST): SpiceDB tuple management (t_workspace relationships)
- Schema language: **ZED** (defines types, relations, permissions)

### The Authorization Flow (Both Backends)

```
HTTP Request
  -> Identity Middleware (decode X-Rh-Identity header)
  -> Authorization Middleware (RBAC or Kessel, selected by config)
    -> [RBAC path]:  HTTP GET to RBAC service, aggregate permissions
    -> [Kessel path]: StreamedListObjects for per-resource IDs,
                      Check fallback for workspace-level wildcard access
  -> Handler receives permissions map: {"openshift.cluster": ["cluster-1", "cluster-2"], ...}
  -> Data layer filters query results by permissions
  -> Response
```

Both backends produce the same `dict[str, dict[str, list]]` (Python) or `map[string][]string` (Go) shape. The handler and data layer code is unchanged.

### Resource Lifecycle (Kessel On-Prem)

Resource creation and deletion in Kessel require two phases:

```
Creation:  ReportResource (Inventory API, gRPC) + POST t_workspace tuple (Relations API, REST)
Deletion:  DeleteResource (Inventory API, gRPC) + DELETE t_workspace tuple (Relations API, REST)
```

The on-prem Kessel configuration disables the CDC-to-consumer pipeline that normally creates tuples automatically. Koku writes and deletes them directly via the Relations API. See [kessel-authorization-delegation-dd.md](./kessel-authorization-delegation-dd.md) Section 6.

---

## 2. Repositories, Branches, and Remotes

### Koku (Python)

| Item | Value |
|---|---|
| On-prem fork | `https://github.com/insights-onprem/koku` |
| Upstream | `https://github.com/project-koku/koku` |
| Branch | `FLPATH-3294/kessel-rebac-integration` |
| Base | Built on top of ELK4N4's `feat/sources` branch ([PR #5895](https://github.com/project-koku/koku/pull/5895)) |
| Status | **Implementation complete.** 203 tests passing across 4 tiers (UT: 111, IT: 23, CT: 8, E2E: 61). All commits pushed. |
| HLD PR | [#5887](https://github.com/project-koku/koku/pull/5887) (open, REVIEW_REQUIRED) |

### ros-ocp-backend (Go)

| Item | Value |
|---|---|
| Repo | `https://github.com/insights-onprem/ros-ocp-backend` |
| Upstream | `https://github.com/RedHatInsights/ros-ocp-backend` |
| Branch | `feature/support_keycloak_jwt_rest_endpoints` |
| Status | **Test plan written** (`docs/kessel-rebac-test-plan.md`, untracked). **No implementation code.** |

### ros-helm-chart

| Item | Value |
|---|---|
| Repo | `https://github.com/insights-onprem/ros-helm-chart` |
| Branch | `feature/FLPATH-2685-external-services-byoi` |
| Status | **6 Kessel-related commits** (23 commits ahead of upstream/main) |

---

## 3. What Has Been Done (Koku -- Complete)

The `koku_rebac` Django app is fully implemented and tested on branch `FLPATH-3294/kessel-rebac-integration`.

### 3.1 Authorization (Adapter Pattern)

- `KesselAccessProvider` uses **StreamedListObjects** (Inventory API v1beta2) to get per-resource IDs, with **Check** fallback for workspace-level wildcard access. This replaced the earlier `CheckPermission`-only approach.
- Write-grants-read parity maintained for all resource types.
- Settings uses workspace-level Check exclusively (capability, not per-resource).
- Key file: [`koku/koku_rebac/access_provider.py`](../../koku/koku_rebac/access_provider.py)

### 3.2 Resource Lifecycle (Dual-Phase)

- `on_resource_created()`: calls ReportResource (Inventory gRPC) + POST t_workspace tuple (Relations REST).
- `on_resource_deleted()`: calls DeleteResource (Inventory gRPC) + DELETE t_workspace tuple (Relations REST).
- `cleanup_orphaned_kessel_resources()`: removes Kessel entries for providers whose data has expired.
- `KesselSyncedResource` model tracks sync state per resource; `kessel_synced` flag reflects actual phase success.
- Key file: [`koku/koku_rebac/resource_reporter.py`](../../koku/koku_rebac/resource_reporter.py)

### 3.3 Sources API Integration

- On-prem Sources API triggers `on_resource_created()` when OCP providers are registered.
- Source deletion preserves Kessel tracking (historical data remains queryable).
- `publish_application_destroy_event()` notifies ros-ocp-backend via Kafka on source deletion.
- Key file: [`koku/sources/api/view.py`](../../koku/sources/api/view.py)

### 3.4 Code Quality (Refactored)

- Constants for SpiceDB namespaces/relations (no magic strings).
- `_get_tuples_url()` DRY helper, narrowed `except Exception` to `requests.RequestException`.
- Thread-safe token cache in `RbacV2Resolver`, `UniqueConstraint` in models.
- `KesselFixture` supports context manager and shared `_poll_until()` for test infra.

### 3.5 Test Coverage

**203 scenarios across 4 tiers, 100% passing** against live Kessel stack (as of 2026-03-02):

| Tier | Count | Scope |
|---|---|---|
| UT | 111 | resource_reporter, access_provider, workspace, client, middleware, models, hooks, config, URLs |
| IT | 23 | Live Kessel: StreamedListObjects, Check, per-resource access, org admin, cross-type isolation, cache |
| CT | 8 | Live SpiceDB: tuple create/delete, cleanup lifecycle, reporter reference, unknown permission |
| E2E | 61 | Full HTTP stack: all provider types, permissions, Sources API, resource-level scoping |

### 3.6 Koku File Map

New files added by this branch (excluding docs, tests, and Kessel dev infra):

| File | Purpose |
|---|---|
| `koku/koku_rebac/__init__.py` | Django app |
| `koku/koku_rebac/access_provider.py` | Kessel + RBAC access providers (adapter pattern) |
| `koku/koku_rebac/apps.py` | Django app config |
| `koku/koku_rebac/client.py` | Singleton gRPC client for Kessel Inventory API |
| `koku/koku_rebac/config.py` | `resolve_authorization_backend()` logic |
| `koku/koku_rebac/exceptions.py` | `KesselError`, `KesselConnectionError` |
| `koku/koku_rebac/models.py` | `KesselSyncedResource` ORM model |
| `koku/koku_rebac/resource_reporter.py` | Resource lifecycle: create, delete, cleanup, tuple management |
| `koku/koku_rebac/urls.py` | URL patterns for koku_rebac app |
| `koku/koku_rebac/workspace.py` | `ShimResolver` (on-prem) and `RbacV2Resolver` (SaaS) |
| `koku/sources/kafka_publisher.py` | Kafka event publisher for source destroy events |
| `koku/sources/api/application_type_views.py` | On-prem Sources compatibility endpoint |
| `koku/sources/api/application_views.py` | On-prem Sources compatibility endpoint |
| `koku/sources/api/source_type_views.py` | On-prem Sources compatibility endpoint |
| `koku/sources/api/source_type_mapping.py` | Provider-type to Sources-type mapping |

Modified files:

| File | Change |
|---|---|
| `koku/koku/settings.py` | Kessel config, cache, AUTHORIZATION_BACKEND |
| `koku/koku/middleware.py` | Kessel access provider integration in IdentityHeaderMiddleware |
| `koku/koku/urls.py` | Include koku_rebac URLs |
| `koku/api/urls.py` | On-prem Sources API routes |
| `koku/api/provider/provider_builder.py` | Hook: `report_ocp_resource()` |
| `koku/cost_models/view.py` | Hook: `perform_create()` reports cost model to Kessel |
| `koku/sources/api/view.py` | On-prem CRUD mixins, Kessel lifecycle |
| `koku/sources/api/serializers.py` | `AdminSourcesSerializer` for on-prem |
| `koku/masu/processor/_tasks/remove_expired.py` | Hook: `cleanup_orphaned_kessel_resources()` |
| `koku/masu/database/ocp_report_db_accessor.py` | Hook: reports OCP resources to Kessel on ingestion |
| `koku/masu/database/gcp_report_db_accessor.py` | Hook: reports GCP resources to Kessel on ingestion |
| `koku/masu/util/aws/common.py` | Hook: reports AWS resources to Kessel on ingestion |
| `koku/masu/processor/accounts/hierarchy/aws/aws_org_unit_crawler.py` | Hook: reports AWS OU resources |
| `koku/masu/processor/azure/azure_report_parquet_summary_updater.py` | Hook: reports Azure resources |
| `docker-compose.yml` | Kafka services for on-prem (with `profiles: ["onprem"]`) |
| `tox.ini` | `ONPREM` env var passthrough |

---

## 4. What Has Been Done (ros-ocp-backend -- Test Plan Only)

The test plan is written at `ros-ocp-backend/docs/kessel-rebac-test-plan.md` (untracked file on the feature branch).

**71 test scenarios** across 3 tiers:

| Tier | Count | Scope |
|---|---|---|
| UT | 55 | Config (11), Kessel client (6), Kessel middleware (10), RBAC middleware (19), Sources API (9) |
| IT | 9 | Full Kessel middleware with real SpiceDB, backend switch verification |
| CT | 7 | ZED schema resolution, permission isolation, group inheritance, tenant isolation |

**No implementation code has been written yet.** The plan drives TDD implementation.

**Known gap (identified 2026-03):** The original test plan uses `Check()` for per-resource authorization. Koku has since switched to `StreamedListObjects` + `Check` fallback (adapter pattern). ros-ocp-backend should align with this pattern for consistency.

---

## 5. What Has Been Done (ros-helm-chart -- Partial)

Kessel-related commits on `feature/FLPATH-2685-external-services-byoi`:

| Commit | What it does |
|---|---|
| `c6af25bd` | Add Helm hook for schema/role provisioning, simplify deploy script |
| `cb134328` | Merge provisioning into migration job, remove separate hook |
| `a4da6a35` | Set default Koku image to rebac-enabled build |
| `5168983f` | Move schema provisioning to `deploy-kessel.sh` |
| `9fdf3998` | Use direct `zed` command for distroless image |
| `ea2f0fc6` | Share `costApplicationTypeId` across Koku and housekeeper |

**Key files modified:**
- `cost-onprem/values.yaml` -- added `costManagement.costApplicationTypeId: "0"`, Kessel/SpiceDB config
- `cost-onprem/templates/_helpers-koku.tpl` -- injects `COST_APPLICATION_TYPE_ID` into all Koku pods
- `cost-onprem/templates/ros/housekeeper/deployment.yaml` -- injects `COST_APPLICATION_TYPE_ID` for ros-ocp-backend housekeeper

---

## 6. Remaining Work (Ordered by Priority)

### 6.1 CRITICAL: Kafka in `docker-compose.yml` Must Be Addressed

ELK4N4's Sources API PR ([#5895](https://github.com/project-koku/koku/pull/5895)) added Kafka/Zookeeper services to `docker-compose.yml` **unconditionally**. This means SaaS developers who run `docker compose up` now get Kafka containers they don't need, consuming resources for nothing.

**Current state:** We added `profiles: ["onprem"]` to gate the services, but the services still exist in the file. The cleanest fix is one of:

| Option | Approach | Tradeoff |
|---|---|---|
| A. Profiles (current) | `profiles: ["onprem"]` on kafka-zookeeper, kafka, init-kafka | Services don't start by default, but lines still in compose file. Requires `COMPOSE_PROFILES=onprem` or `--profile onprem` to activate. |
| B. Separate file | Move Kafka to `docker-compose.onprem.yml` | Clean separation. On-prem devs use `docker compose -f docker-compose.yml -f docker-compose.onprem.yml up`. |
| C. Remove entirely | Remove from compose, rely on Kessel stack or external Kafka | Cleanest, but on-prem devs must set up Kafka independently. |

**Action needed:** Decide with the upstream Koku team which approach they prefer. This should be resolved before the branch is merged.

**Why Kafka is needed on-prem:** Koku's `koku-listener` service consumes `platform.sources.event-stream` from Kafka to react to source create/delete events. In SaaS, Kafka is provided by the platform. On-prem has no platform Kafka, so a local broker is needed. The `init-kafka` service creates the `platform.sources.event-stream` topic.

### 6.2 CRITICAL: Upstream ELK4N4 Sources PR ([#5895](https://github.com/project-koku/koku/pull/5895))

Our branch (`FLPATH-3294/kessel-rebac-integration`) is built **on top of** ELK4N4's `feat/sources` branch. This means:

- **PR #5895 MUST merge first** (or be rebased into our branch) before our Kessel PR can land on `main`.
- PR #5895 status: OPEN, REVIEW_REQUIRED. Comments from bacciotti, myersCody, jordigilh.
- **Last 3 commits in #5895** (triaged 2026-03-02): `skipUnless`/`skipIf` decorators on Sources tests, tox.ini ONPREM passthrough, CI step for ONPREM tests, Trino version bump. **No regressions** against our kessel code (verified by running all 203 tests).

### 6.3 HIGH: Koku PR Creation

The Kessel integration branch (`FLPATH-3294/kessel-rebac-integration`) needs a PR. Options:

| Target | When |
|---|---|
| `insights-onprem/koku` (on-prem fork) | If deploying on-prem independently of upstream merge |
| `project-koku/koku` (upstream) | After PR #5895 merges; our branch rebases on top of main |

**HLD PR [#5887](https://github.com/project-koku/koku/pull/5887)** is still open under review. Comments from masayag, lcouzens. May need to be updated to reflect the latest architectural changes (StreamedListObjects pattern, dual-phase lifecycle).

### 6.4 HIGH: ZED Schema Upstream PR ([FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319))

The production ZED schema in [`rbac-config`](https://github.com/RedHatInsights/rbac-config) needs a PR to wire **all 23** `cost_management_*` permissions (13 OCP + 10 cloud) through `rbac/role_binding` and `rbac/tenant`. **The PR has NOT been opened yet.** Cloud permissions are included so Koku and SaaS are ready when SaaS onboards Kessel.

The exact ZED additions (23 permissions on `rbac/role_binding` + 23 on `rbac/tenant`) are specified in [zed-schema-upstream-delta.md](./zed-schema-upstream-delta.md) Section 2, Gap G-1, with copy-paste-ready schema blocks.

**This blocks E2E testing on production-like schemas.** Currently, all tests use the local development schema in `dev/kessel/schema.zed`.

### 6.5 HIGH: ros-ocp-backend Implementation

Implement the Kessel integration in Go, driven by the test plan (`docs/kessel-rebac-test-plan.md`). Follow TDD (write tests first, then code).

**New files to create:**

| File | Purpose |
|---|---|
| `internal/kessel/client.go` | Kessel gRPC client wrapper |
| `internal/api/middleware/kessel.go` | Kessel authorization middleware (Echo middleware) |

**Files to modify:**

| File | Change |
|---|---|
| `internal/config/config.go` | Add `AuthorizationBackend`, `KesselRelationsURL`, `KesselRelationsTLS`, `SpiceDBPresharedKey` fields |
| `internal/api/server.go` | Switch on `AuthorizationBackend` inside `if cfg.RBACEnabled` guard |
| `internal/utils/sources/sources_api.go` | Add `COST_APPLICATION_TYPE_ID` env var check before HTTP fallback |
| `go.mod` | Add `github.com/project-kessel/relations-api` and `github.com/authzed/authzed-go` |

**Files unchanged:**
- `internal/api/middleware/rbac.go` -- existing RBAC code stays as-is
- `internal/model/recommendation_set.go` (`add_rbac_filter`) -- unchanged, gated on `RBACEnabled`
- `internal/api/handlers.go` -- reads `user.permissions` from context (works with both backends)

**Implementation order (dependency-driven):**

1. Config fields (UT-CFG-BACKEND-*)
2. Kessel client (UT-KESSEL-CHECK-*)
3. Kessel middleware (UT-MW-AUTH-*)
4. Server wiring (UT-MW-BACKEND-001)
5. Sources API env var (UT-SRC-APPID-*)
6. RBAC tests (UT-RBAC-PERM-*, UT-RBAC-ACCESS-*) -- regression coverage
7. Integration tests (IT-MW-AUTH-*, IT-MW-BACKEND-001)
8. Contract tests (CT-KESSEL-*)

**Critical design gap:** The test plan uses `Check()` per resource. Koku uses `StreamedListObjects` + `Check` fallback. The ros-ocp-backend implementation should align with the adapter pattern:
1. Call `StreamedListObjects` to get resource IDs for per-resource types (cluster, node, project)
2. Use `Check` for workspace-level permissions only
3. See Koku's [`access_provider.py`](../../koku/koku_rebac/access_provider.py) as the reference implementation

### 6.6 MEDIUM: ros-helm-chart Integration

After ros-ocp-backend implementation is complete:

- Add Kessel env vars to ros-ocp-backend deployment templates (`AUTHORIZATION_BACKEND`, `KESSEL_RELATIONS_URL`, `KESSEL_RELATIONS_CA_PATH`, `SPICEDB_PRESHARED_KEY`)
- Test full E2E stack on OCP (Kessel + Koku + ros-ocp-backend)

### 6.7 MEDIUM: Uncommitted Changes to Commit

Three files have been modified but not committed:

| File | Change | Suggested commit |
|---|---|---|
| `docker-compose.yml` | Added `profiles: ["onprem"]` to Kafka services | With this handover update |
| `koku/koku_rebac/test/test_models.py` | Fixed `test_unique_constraint` (was checking deprecated `unique_together` instead of `UniqueConstraint`) | With this handover update |
| This file | Updated handover document | With this handover update |

### 6.8 LOW: Related Open PRs to Track

These PRs are open in `project-koku/koku` and may affect or interact with Kessel work:

| PR | Author | Title | Relevance |
|---|---|---|---|
| [#5895](https://github.com/project-koku/koku/pull/5895) | ELK4N4 | Add Sources API compatibility endpoints | **Prerequisite** -- our branch depends on this |
| [#5887](https://github.com/project-koku/koku/pull/5887) | jordigilh | docs: add Kessel/ReBAC OCP integration HLD | Design document for review |
| [#5905](https://github.com/project-koku/koku/pull/5905) | myersCody | Add makefile command for onprem local dev | Development ergonomics |
| [#5918](https://github.com/project-koku/koku/pull/5918) | ydayagi | [FLPATH-3323] Add AWS self-hosted/on-prem support | AWS on-prem provider; may need Kessel resource reporting hooks |
| [#5917](https://github.com/project-koku/koku/pull/5917) | pgarciaq | Add AGENTS.md | AI coding assistant conventions |

---

## 7. Key Differences Between Koku and ros-ocp-backend

| Aspect | Koku (Python) | ros-ocp-backend (Go) |
|---|---|---|
| Config flag for auth | `ONPREM` -> `AUTHORIZATION_BACKEND` (derived) | `RBAC_ENABLE` (master switch) + `AUTHORIZATION_BACKEND` |
| Backend values | `"rbac"` / `"rebac"` | `"rbac"` / `"kessel"` |
| Kessel API | **StreamedListObjects** + Check fallback via Inventory API v1beta2 gRPC | Should align with StreamedListObjects pattern (**not yet implemented**) |
| Permission count | 10 resource types (AWS, Azure, GCP, OCP, cost_model, settings) | 3 resource types (openshift.cluster, .node, .project) |
| Data filtering | `query_params._set_access()` | `add_rbac_filter()` in GORM |
| On Kessel outage | HTTP 424 (Failed Dependency) | HTTP 403 (Forbidden) -- matches existing RBAC behavior |
| DB filter guard | Always runs when `AUTHORIZATION_BACKEND == "rebac"` | Gated on `cfg.RBACEnabled` (shared flag for both backends) |
| Local dev (no auth) | Not applicable (`ONPREM` is always set in prod) | `RBAC_ENABLE=false` disables all auth |

### Permission Mapping (ros-ocp-backend only)

| RBAC permission string | Kessel CheckPermission relation | ros-ocp-backend map key |
|---|---|---|
| `cost-management:openshift.cluster:read` | `cost_management_openshift_cluster_read` | `openshift.cluster` |
| `cost-management:openshift.node:read` | `cost_management_openshift_node_read` | `openshift.node` |
| `cost-management:openshift.project:read` | `cost_management_openshift_project_read` | `openshift.project` |

---

## 8. Known Bugs (Pre-existing, Not Introduced by This Work)

### ros-ocp-backend

| Scenario | Bug | Impact |
|---|---|---|
| UT-RBAC-ACCESS-006 | `request_user_access()` panics on nil response when RBAC host is unreachable (`rbac.go:93-97`) | Crash instead of graceful 403 on network failure |
| UT-RBAC-PERM-013 | `aggregate_permissions()` panics on permission strings with no colons (`rbac.go:42`) | Crash on malformed RBAC data |
| UT-SRC-APPID-009 | `GetCostApplicationID()` panics on empty `data` array from Sources API (`sources_api.go:31`) | Crash if Sources API returns no applications |

These are documented as `Expect(...).To(Panic())` tests and annotated as "expected to change when the bug is fixed."

---

## 9. How to Run Tests

### 9.1 Prerequisites

```bash
# Start Kessel stack (SpiceDB + Relations API + Inventory API)
podman compose -f dev/kessel/docker-compose.yml up -d

# Start test PostgreSQL (for Django ORM tests)
podman run -d --name koku-test-db --replace -p 15432:5432 \
  -e POSTGRES_DB=test -e POSTGRES_USER=koku_tester -e POSTGRES_PASSWORD=password postgres:16

# Start Redis (for Celery result backend in E2E tests)
podman run -d --name koku-test-redis --replace -p 6379:6379 redis:7

# Verify all containers are running
podman ps --format "{{.Names}} {{.Status}}" | grep -E "kessel|koku-test|redis"
```

Expected containers: `kessel-test-database-1`, `kessel-test-spicedb-1`, `kessel-test-relations-api-1`, `kessel-test-inventory-api-1`, `koku-test-db`, `koku-test-redis`.

### 9.2 Koku Tests

The common environment prefix for all tiers:

```bash
cd /path/to/koku

export COMMON_ENV="ONPREM=True DJANGO_SETTINGS_MODULE=koku.settings PYTHONPATH=koku:. \
  PROMETHEUS_MULTIPROC_DIR=/tmp REDIS_HOST=localhost \
  DATABASE_USER=koku_tester DATABASE_PASSWORD=password DATABASE_NAME=test \
  POSTGRES_SQL_SERVICE_HOST=localhost POSTGRES_SQL_SERVICE_PORT=15432"
```

Run each tier:

```bash
# Tier 1: Unit Tests (111 tests, ~6s, no live Kessel needed)
env $COMMON_ENV .venv-test/bin/python koku/manage.py test --noinput -v 2 \
  koku_rebac.test.test_resource_reporter \
  koku_rebac.test.test_access_provider \
  koku_rebac.test.test_workspace \
  koku_rebac.test.test_client \
  koku_rebac.test.test_middleware_rebac \
  koku_rebac.test.test_models \
  koku_rebac.test.test_hooks \
  koku_rebac.test.test_config \
  koku_rebac.test.test_urls

# Tier 2: Integration Tests (23 tests, ~12s, needs live Kessel + DB)
env $COMMON_ENV ENABLE_KESSEL_TEST=1 \
  .venv-test/bin/python koku/manage.py test --noinput -v 2 \
  koku_rebac.test.test_integration

# Tier 3: Contract Tests (8 tests, ~5s, needs live Kessel)
env $COMMON_ENV ENABLE_KESSEL_TEST=1 \
  .venv-test/bin/python koku/manage.py test --noinput -v 2 \
  koku_rebac.test.test_contract

# Tier 4: End-to-End Tests (61 tests, ~22s, needs live Kessel + DB + Redis)
env $COMMON_ENV ENABLE_KESSEL_TEST=1 \
  .venv-test/bin/python koku/manage.py test --noinput -v 2 \
  koku_rebac.test.test_e2e_regression
```

**Important notes:**
- `ENABLE_KESSEL_TEST=1` is required for IT, CT, and E2E tiers (tests skip without it).
- `ONPREM=True` must be set at **process start**, not via `@override_settings`, because Sources viewset mixins are resolved at import time.
- Use `manage.py test`, not `pytest`, for IT and E2E tiers. Django's `KokuTestRunner` creates tenant schema tables needed by `IamTestCase`.
- `REDIS_HOST=localhost` is required because Koku's `settings.py` defaults to `"redis"` (container networking hostname).

### 9.3 ros-ocp-backend (Once Implemented)

```bash
cd /path/to/ros-ocp-backend

# Unit tests
go test ./internal/...

# Integration tests (need real Kessel stack)
go test -tags integration ./internal/...

# Contract tests (need real Kessel stack)
go test -tags contract ./internal/...
```

---

## 10. Gotchas and Lessons Learned

These are hard-won insights that will save the incoming team significant debugging time:

### 10.1 Kessel Tuple Creation (On-Prem Gap)

The Inventory API's `ReportResource` does **not** automatically create SpiceDB tuples on-prem. The SaaS pipeline uses a CDC outbox pattern (Debezium + Kafka + consumer), but the on-prem config (`eventing: stdout`, `consumer: enabled: false`) disables this entirely.

**Solution:** Koku calls the Relations API directly to create and delete `t_workspace` tuples. See `_create_resource_tuples()` and `_delete_resource_tuples()` in `resource_reporter.py`.

### 10.2 `@override_settings(ONPREM=True)` Is Too Late for Sources

The Sources viewset determines its HTTP methods (`CreateModelMixin`, `"post"`) at **module import time** based on `settings.ONPREM`. `@override_settings` at test runtime doesn't help. Set `ONPREM=True` in the environment before the process starts.

### 10.3 `pytest` vs `manage.py test`

Running `pytest` directly for IT/E2E tests causes `UndefinedTable: relation "user_settings" does not exist` because `pytest` bypasses Koku's `KokuTestRunner`, which creates tenant schema tables. Always use `manage.py test` for tests that extend `IamTestCase`.

### 10.4 SpiceDB Eventual Consistency

SpiceDB tuples may not be immediately visible after creation. The `KesselFixture` includes `_wait_for_consistency()` and `_poll_until()` helpers with exponential backoff. If tests flake with "resource not visible", increase the polling timeout, don't add `time.sleep()`.

### 10.5 ReporterReference Must Not Be Nil

Kessel Inventory API panics if `ReporterReference` is nil in `Check` or `ReportResource` requests. All requests must set `reporter_instance_id` (we use `"cost_management"`). This is covered by contract test `test_reporter_reference_not_nil`.

### 10.6 `DeleteResource` Only Removes Inventory Metadata

Calling `DeleteResource` on the Inventory API does **not** remove the SpiceDB tuple. `StreamedListObjects` is backed by SpiceDB, not Inventory. A full cleanup requires both `DeleteResource` (Inventory) and `DELETE /api/authz/v1beta1/tuples` (Relations API).

### 10.7 ELK4N4's Test Skip Decorators

ELK4N4's latest commits add `@unittest.skipUnless(settings.ONPREM)` and `@unittest.skipIf(settings.ONPREM or settings.DEVELOPMENT)` to Sources tests. This means:
- On-prem-only tests (application_types, applications, source_types) skip in SaaS mode -- correct.
- SaaS-only tests (405 assertions for PATCH/PUT/DELETE) skip in on-prem mode -- correct.
- `tox.ini` defaults `ONPREM=False`. To run on-prem tests via tox: `ONPREM=True pipenv run tox -- sources.test`.

---

## 11. Key Documents (Reading Order)

For a new team, read in this order:

| # | Document | Location | Why |
|---|---|---|---|
| 1 | **This handoff** | You're reading it | Big picture, what's done, what's pending |
| 2 | **On-prem authorization backend** | [`koku/docs/architecture/onprem-authorization-backend.md`](../onprem-authorization-backend.md) | Decision doc: Kessel vs RBAC v1 vs RBAC v2 for on-prem |
| 3 | **Authorization delegation DD** | [`kessel-authorization-delegation-dd.md`](./kessel-authorization-delegation-dd.md) | Adapter vs full delegation, workspace tuple lifecycle |
| 4 | **Koku detailed design** | [`kessel-ocp-detailed-design.md`](./kessel-ocp-detailed-design.md) | Full architecture spec for the Koku side |
| 5 | **Koku test plan** | [`kessel-ocp-test-plan.md`](./kessel-ocp-test-plan.md) | 203 scenarios, IEEE 829 format, all implemented |
| 6 | **ros-ocp-backend test plan** | `ros-ocp-backend/docs/kessel-rebac-test-plan.md` | Drives TDD implementation; 71 scenarios |
| 7 | **ZED schema delta** | [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md) | Schema changes needed in rbac-config |
| 8 | **Kessel dev stack README** | [`dev/kessel/README.md`](../../dev/kessel/README.md) | How to run SpiceDB + Relations API + Inventory API locally |

---

## 12. Getting Started Checklist

1. Read documents 1-4 from Section 11 (this handoff, decision doc, delegation DD, detailed design)
2. Check out the Koku branch: `git checkout FLPATH-3294/kessel-rebac-integration`
3. Start infrastructure (Section 9.1) and run all 4 Koku test tiers (Section 9.2) to verify the environment works
4. Resolve the Kafka/docker-compose.yml approach (Section 6.1) with upstream Koku team
5. Ensure ELK4N4's PR #5895 is progressing toward merge (Section 6.2)
6. Create the Koku implementation PR (Section 6.3)
7. Open the ZED schema PR in rbac-config (Section 6.4)
8. Read the ros-ocp-backend source files listed in Section 6.5 (config, server, middleware, handlers, model)
9. Set up Podman Compose for the Kessel stack for IT and CT tests
10. Create a feature branch in ros-ocp-backend for the Kessel implementation
11. Start TDD implementation following the order in Section 6.5, using the test plan as the spec -- align with StreamedListObjects pattern, not Check-only
12. After ros-ocp-backend implementation, update the Helm chart (Section 6.6)

---

## 13. Contacts and Links

| Resource | URL |
|---|---|
| Koku (on-prem fork) | https://github.com/insights-onprem/koku |
| Koku (upstream) | https://github.com/project-koku/koku |
| ros-ocp-backend | https://github.com/insights-onprem/ros-ocp-backend |
| ros-helm-chart | https://github.com/insights-onprem/ros-helm-chart |
| Kessel Project | https://github.com/project-kessel |
| Kessel Inventory API | https://github.com/project-kessel/inventory-api |
| Kessel Relations API (Go stubs) | https://github.com/project-kessel/relations-api |
| authzed-go (SpiceDB Go client) | https://github.com/authzed/authzed-go |
| RBAC Config (ZED schema, roles) | https://github.com/RedHatInsights/rbac-config |
| HLD PR | https://github.com/project-koku/koku/pull/5887 |
| Sources API PR (ELK4N4) | https://github.com/project-koku/koku/pull/5895 |
| Jira: Koku Kessel | https://issues.redhat.com/browse/FLPATH-3294 |
| Jira: ros-ocp-backend Kessel | https://issues.redhat.com/browse/FLPATH-3338 |
| Jira: ZED schema upstream PR | https://issues.redhat.com/browse/FLPATH-3319 |
| Jira: Parent story | https://issues.redhat.com/browse/FLPATH-2690 |
