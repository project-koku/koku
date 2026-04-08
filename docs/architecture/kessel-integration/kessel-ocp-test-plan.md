# Kessel/ReBAC Integration -- Test Plan

| Field         | Value                                                                        |
|---------------|------------------------------------------------------------------------------|
| Jira          | [FLPATH-3294](https://issues.redhat.com/browse/FLPATH-3294)                 |
| DD Reference  | [kessel-ocp-detailed-design.md](./kessel-ocp-detailed-design.md)            |
| Author        | Jordi Gil                                                                    |
| Status        | Draft                                                                        |
| Created       | 2026-02-18                                                                  |
| Last updated  | 2026-02-26 (tuple lifecycle scenarios added)                                |

## Table of Contents

1. [Conventions](#1-conventions)
2. [Tier 1 -- Unit Tests (UT)](#2-tier-1----unit-tests-ut)
3. [Tier 2 -- Integration Tests (IT)](#3-tier-2----integration-tests-it)
4. [Tier 3 -- Contract Tests (CT)](#4-tier-3----contract-tests-ct)
5. [Tier 4 -- E2E Tests (E2E)](#5-tier-4----e2e-tests-e2e)
   - [E2E Regression: UI Acceptance Scenarios (s1-s53)](#e2e-regression-ui-acceptance-scenarios-s1-s53)
6. [Coverage Summary](#6-coverage-summary)

---

## 1. Conventions

### 1.1 Scenario ID Format

`{TIER}-{MODULE}-{FEATURE}-{NNN}`

| Segment | Values | Description |
|---------|--------|-------------|
| TIER | `UT`, `IT`, `CT`, `E2E` | Unit, Integration, Contract, End-to-End |
| MODULE | `KESSEL`, `MW`, `SETTINGS`, `MASU`, `API`, `SRC`, `COSTMODEL` | Koku module where the test code lives |
| FEATURE | Short mnemonic | Feature under test |
| NNN | `001`-`999` | Sequential scenario number |

### 1.2 Module Reference

| Code | Koku module | Covers |
|------|-------------|--------|
| `KESSEL` | `koku/koku_rebac/` | access_provider, client, resource_reporter, models, workspace resolver |
| `MW` | `koku/koku/middleware.py` | Middleware integration |
| `SETTINGS` | `koku/koku/settings.py` | Configuration and startup |
| `MASU` | `koku/masu/` | Pipeline hook |
| `API` | `koku/api/` | ProviderBuilder hook |
| `SRC` | `koku/sources/api/` | Sources API CRUD, CMMO compatibility, Kessel resource lifecycle |
| `COSTMODEL` | `koku/cost_models/` | CostModelViewSet hook |
| ~~`REL`~~ | ~~`koku/koku_rebac/test/test_contract.py`~~ | ~~Relations API contract~~ (RETIRED -- externalized to `kessel-admin.sh`) |
| ~~`LOOKUP`~~ | ~~`koku/koku_rebac/test/test_contract.py`~~ | ~~LookupResources contract~~ (RETIRED -- replaced by Inventory API Check/StreamedListObjects) |

### 1.3 Feature Mnemonics

| Mnemonic | Feature |
|----------|---------|
| `AP` | AccessProvider (Check, StreamedListObjects, _view/_edit compounds) |
| `CL` | Kessel gRPC Client (Inventory API stub, TLS/CA) |
| `RR` | Resource Reporter (ReportResource, write_visibility, representations) |
| `WS` | Workspace Resolver (ShimResolver, RbacV2Resolver) |
| `MDL` | Models (KesselSyncedResource) |
| `AUTH` | Auth dispatch / cache |
| `CFG` | Configuration / settings |
| `SYNC` | Pipeline sync |
| `PB` | ProviderBuilder hook |
| `CM` | Cost model hook |
| `CREATE` | Sources API -> Kessel resource creation |
| `RETAIN` | Source deletion behavior: integration deleted, OCP resources retained (historical data preserved) |
| `ONPREM` | ONPREM flag Sources CRUD gate |
| `FLOW` | Full auth flow |
| `TW` | Tuple/Workspace lifecycle (t_workspace creation and deletion via Relations API) |
| ~~`SEED`~~ | ~~Role seeding command~~ (RETIRED) |
| ~~`SCHEMA`~~ | ~~Schema update command~~ (RETIRED) |
| ~~`VIEW`~~ | ~~Access Management API views~~ (RETIRED) |
| ~~`SER`~~ | ~~Access Management API serializers~~ (RETIRED) |
| ~~`GRP`~~ | ~~Group management~~ (RETIRED) |
| ~~`URL`~~ | ~~URL registration~~ (RETIRED) |
| ~~`REL`~~ | ~~Relations API CRUD~~ (RETIRED) |
| ~~`LOOKUP`~~ | ~~LookupResources~~ (RETIRED) |

### 1.4 Priority Levels

| Level | Meaning | Triage guidance |
|-------|---------|-----------------|
| P0 (Critical) | Core contract, blocks all downstream | Must fix immediately; blocks PR merge |
| P1 (High) | Key feature, significant user impact | Fix before phase checkpoint |
| P2 (Medium) | Important but not blocking | Fix before final PR merge |
| P3 (Low) | Defensive, unlikely paths | Can defer to follow-up |

### 1.5 Per-Scenario Format

Each scenario follows an IEEE 829-inspired structure with Priority, Business Value, Fixtures, BDD Steps, and Acceptance Criteria.

### 1.6 Tier Infrastructure

| Tier | Runner | CI? | Kessel? |
|------|--------|-----|---------|
| UT | Django `manage.py test` / tox | Yes | Mocked gRPC |
| IT | Django `manage.py test` + `@override_settings` | Yes | Mocked gRPC |
| CT | Django `manage.py test` with Podman Compose Kessel stack | Local only | Real gRPC stack |
| E2E | IQE plugin with Kessel markers | No (OCP) | Full stack |

---

## 2. Tier 1 -- Unit Tests (UT)

Coverage target: >80% on `koku/koku_rebac/` module.

---

### UT-KESSEL-AP-001: Authorized user sees only their permitted OCP clusters

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | A user authorized for 2 specific clusters must see cost data for exactly those clusters and no others |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` returning mock where `inventory_stub.StreamedListObjects` returns `["cluster-uuid-1", "cluster-uuid-2"]` for `cost_management/openshift_cluster`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_CACHE_TIMEOUT=300)`

**Steps:**
- **Given** a user who has Kessel role bindings granting read access to 2 OCP clusters
- **When** the middleware resolves their access through `KesselAccessProvider`
- **Then** the user's access dict enables the query layer to filter OCP cost data to exactly `cluster-uuid-1` and `cluster-uuid-2`
- **And** the access dict is consumable by every resource type view and permission class without modification

**Acceptance Criteria:**
- The access dict produced by `KesselAccessProvider` is structurally identical to what `RbacService` would produce, ensuring the query layer works without changes
- The user's authorized cluster UUIDs are the exact values returned by `StreamedListObjects`, with no interpretation or transformation
- Every resource type defined in `RESOURCE_TYPES` has a corresponding entry in the access dict, even if the user has no access to that type

---

### UT-KESSEL-AP-002: User with no Kessel permissions is denied all access

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | A user with no role bindings in Kessel must be denied access to all cost management data |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` returning mock where `inventory_stub.Check` returns `ALLOWED_FALSE` for all non-OCP types and `inventory_stub.StreamedListObjects` returns `[]` for all OCP types
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user who has no Kessel role bindings for any cost management resource
- **When** the middleware resolves their access through `KesselAccessProvider`
- **Then** the user is denied access to all cost management endpoints, matching the behavior when RBAC returns no ACLs

**Acceptance Criteria:**
- The middleware receives a signal equivalent to "no permissions" that permission classes use to deny access
- This behavior is identical to how RBAC handles users with no cost-management roles

---

### UT-KESSEL-AP-003: Kessel outage degrades gracefully (fail-open per-type)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When Kessel is unavailable, users see no data (empty access) rather than receiving incorrect access or crashing. Silent degradation is the current design — monitoring is required to detect it |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` where `inventory_stub.Check` raises `grpc.RpcError` / `Exception`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** Kessel's Inventory API is unreachable (all gRPC calls raise exceptions)
- **When** the middleware attempts to resolve a user's access through `KesselAccessProvider`
- **Then** the provider catches all exceptions internally (in `_check_workspace_permission` and `_streamed_list_objects`), returning `False`/`[]` for each type. The overall access dict contains empty lists for every resource type

**Acceptance Criteria:**
- `_check_workspace_permission` catches `Exception` and returns `False` — no exception propagates
- `_streamed_list_objects` catches `Exception` and returns `[]` — no exception propagates
- The overall access dict is structurally valid (all types present) but contains no grants (empty lists)
- Errors are logged with `LOG.exception(...)` including resource type and permission, enabling operators to diagnose via log monitoring
- **Note**: `KesselConnectionError` is defined in `koku_rebac/exceptions.py` and caught by middleware, but the current `KesselAccessProvider` does not raise it. The middleware handler exists as a safety net for future explicit raises

---

### UT-KESSEL-AP-004: Every cost management resource type is queryable through Kessel

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If a resource type is missing from the Kessel mapping, users cannot be authorized for that resource type, silently breaking access control |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** Koku defines 11 resource types in `RESOURCE_TYPES` (aws.account, aws.organizational_unit, gcp.account, gcp.project, azure.subscription_guid, openshift.cluster, openshift.node, openshift.project, integration, cost_model, settings)
- **When** the `KOKU_TO_KESSEL_TYPE_MAP` constant and the `RESOURCE_TYPES` operation definitions are validated
- **Then** every Koku resource type maps to a Kessel resource type, and operations map to `_view`/`_edit` compound permission suffixes

**Acceptance Criteria:**
- All 11 Koku resource types have Kessel type mappings (e.g., `openshift.cluster` -> `cost_management/openshift_cluster`, `integration` -> `cost_management/integration`)
- Read operations use `_view` compound permission; write operations use `_edit` compound permission
- The provider issues a minimum of 13 workspace-level `Check` calls: 10 per-resource types × read + cost_model write + settings read + settings write. `StreamedListObjects` is called as a fallback only when a workspace `Check` returns DENIED for a per-resource type. The workspace-check-first pattern ensures that users with org-wide roles (e.g., cost-administrator) receive wildcard access without per-resource enumeration
- No runtime `KeyError` is possible when iterating `RESOURCE_TYPES`

---

### UT-KESSEL-AP-005: User with partial access sees only authorized resources across types

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A real-world user (e.g., OCP viewer with no cloud access) must see OCP cost data but not AWS/Azure/GCP data |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` returning: `inventory_stub.StreamedListObjects` yields 2 clusters for `openshift_cluster`; `inventory_stub.Check` returns `ALLOWED_FALSE` for `aws_account` `_view`, `ALLOWED_TRUE` for `cost_model` `_view` and `_edit`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user authorized for 2 OCP clusters and 1 cost model, but no AWS accounts
- **When** the middleware resolves their access through `KesselAccessProvider`
- **Then** the user can view OCP cost reports filtered to their 2 clusters, can read and write their cost model, and is denied access to any AWS cost data

**Acceptance Criteria:**
- OCP cluster access contains exactly the 2 authorized cluster UUIDs from `StreamedListObjects`
- AWS account access is empty (Check returned DENIED), resulting in no AWS data visible to the user
- Cost model access includes wildcard `["*"]` for both read and write operations (write grants read)
- The access dict is directly usable by `QueryParameters._set_access()` and `CostModelViewSet.get_queryset()` without transformation

---

### UT-KESSEL-AP-006: Application uses the correct authorization backend based on deployment configuration

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | If the wrong backend is selected, all authorization decisions are incorrect -- RBAC users hit Kessel (which may not exist) or Kessel users hit RBAC (which doesn't exist on-prem) |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")` and `@override_settings(AUTHORIZATION_BACKEND="rbac")` for separate sub-tests

**Steps:**
- **Given** a deployment configured with `AUTHORIZATION_BACKEND="rebac"`
- **When** `get_access_provider()` is called
- **Then** the factory returns a `KesselAccessProvider` instance
- **Given** a deployment configured with `AUTHORIZATION_BACKEND="rbac"`
- **When** `get_access_provider()` is called
- **Then** the factory returns an `RBACAccessProvider` instance

**Acceptance Criteria:**
- ReBAC configuration produces a provider that calls Kessel gRPC APIs
- RBAC configuration produces a provider that calls the RBAC HTTP API
- The factory consistently returns the correct provider type for the configured backend

---

### UT-KESSEL-CL-001: Development deployments connect to Kessel without TLS

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Development and non-TLS environments must be able to connect to Kessel without certificate configuration |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_INVENTORY_CONFIG={"host": "localhost", "port": 9081}, KESSEL_CA_PATH="")`
- `@patch("grpc.insecure_channel")`

**Steps:**
- **Given** a development deployment with no CA certificate configured (`KESSEL_CA_PATH` is empty)
- **When** the Kessel client establishes a connection to the Inventory API
- **Then** the connection is made over an insecure (plaintext) gRPC channel to `localhost:9081`

**Acceptance Criteria:**
- The client connects successfully without requiring TLS certificates when `KESSEL_CA_PATH` is empty
- No TLS-related errors or certificate validation occurs
- The connection target matches the configured host and port

---

### UT-KESSEL-CL-002: Production deployments connect to Kessel with TLS encryption

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Production gRPC traffic must be encrypted; plaintext connections would expose authorization data |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_INVENTORY_CONFIG={"host": "kessel.example.com", "port": 443}, KESSEL_CA_PATH="/etc/pki/tls/ca.pem")`
- `@patch("grpc.secure_channel")`
- `@patch("grpc.ssl_channel_credentials")`
- `@patch("builtins.open", mock_open(read_data=b"PEM_DATA"))`

**Steps:**
- **Given** a production deployment with a CA certificate configured at `KESSEL_CA_PATH`
- **When** the Kessel client establishes a connection to the Inventory API
- **Then** the connection is made over a TLS-encrypted gRPC channel using the specified CA certificate

**Acceptance Criteria:**
- The client reads the CA certificate from the configured `KESSEL_CA_PATH`
- The client uses `grpc.ssl_channel_credentials(root_certificates=PEM_DATA)` for the channel
- The connection targets the production host and port over a secure channel
- Plaintext connections are not attempted

---

### UT-KESSEL-CL-003: Concurrent requests share a single Kessel connection

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | Creating a new gRPC connection per request would exhaust resources under load; all requests must share a single managed connection |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- Reset `_client_instance` to `None`
- `@patch("koku_rebac.client.KesselClient")`

**Steps:**
- **Given** the Kessel client has not been initialized yet
- **When** 10 concurrent HTTP requests trigger authorization checks simultaneously
- **Then** all 10 requests share the same Kessel client and gRPC channel

**Acceptance Criteria:**
- Only one gRPC connection is established regardless of concurrency
- No race condition causes duplicate client initialization
- All threads receive authorization responses from the shared connection

---

### UT-KESSEL-CL-004: Custom CA certificate is loaded from the configured path

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Air-gapped and on-prem environments use self-signed or internal CA certificates. The gRPC channel must load the specified CA for TLS trust, or connections to Kessel fail with certificate validation errors |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_INVENTORY_CONFIG={"host": "kessel.internal", "port": 443}, KESSEL_CA_PATH="/custom/ca.pem")`
- `@patch("builtins.open", mock_open(read_data=b"CUSTOM_CA_PEM"))`
- `@patch("grpc.ssl_channel_credentials")`

**Steps:**
- **Given** a deployment with `KESSEL_CA_PATH` pointing to a custom CA file
- **When** the Kessel client builds the gRPC channel
- **Then** the CA certificate is read from `/custom/ca.pem` and passed to `grpc.ssl_channel_credentials(root_certificates=CUSTOM_CA_PEM)`

**Acceptance Criteria:**
- The file at `KESSEL_CA_PATH` is opened and read
- The PEM data is passed as `root_certificates` to `grpc.ssl_channel_credentials()`
- A `grpc.secure_channel` is created with these credentials

---

### UT-KESSEL-CL-005: Empty CA path produces insecure channel for local development

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | Local development environments (e.g., `docker-compose`) run Kessel without TLS. An empty `KESSEL_CA_PATH` must produce an insecure channel so developers can connect without certificate setup |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_INVENTORY_CONFIG={"host": "localhost", "port": 9081}, KESSEL_CA_PATH="")`
- `@patch("grpc.insecure_channel")`

**Steps:**
- **Given** a development deployment with `KESSEL_CA_PATH` set to an empty string
- **When** the Kessel client builds the gRPC channel
- **Then** `grpc.insecure_channel` is used (not `grpc.secure_channel`)

**Acceptance Criteria:**
- When `KESSEL_CA_PATH` is empty, `grpc.insecure_channel` is called
- No attempt is made to read a CA file or create SSL credentials
- The channel connects to the configured host and port

---

### UT-KESSEL-CL-006: Client exposes only the Inventory API stub

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | After the migration to Inventory API v1beta2, the client must NOT expose Relations API stubs (`check_stub`, `lookup_stub`, `tuples_stub`). Leftover stubs could lead to accidental direct SpiceDB usage, bypassing the Inventory API contract |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_INVENTORY_CONFIG={"host": "localhost", "port": 9081}, KESSEL_CA_PATH="")`

**Steps:**
- **Given** a `KesselClient` instance
- **When** the client's attributes are inspected
- **Then** the client has an `inventory_stub` attribute and does NOT have `check_stub`, `lookup_stub`, or `tuples_stub`

**Acceptance Criteria:**
- `hasattr(client, "inventory_stub")` is True
- `hasattr(client, "check_stub")` is False (Relations API removed)
- `hasattr(client, "lookup_stub")` is False (Relations API removed)
- `hasattr(client, "tuples_stub")` is False (Relations API removed)

---

### UT-KESSEL-RR-001: RBAC deployments are completely unaffected by Kessel resource tracking

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | SaaS deployments using RBAC must incur zero overhead from Kessel -- no gRPC connections, no database writes, no latency impact |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rbac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")`
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects")`

**Steps:**
- **Given** a SaaS deployment configured with RBAC authorization
- **When** a new OCP cluster is registered and the resource reporter is invoked
- **Then** no gRPC connections to Kessel are attempted and no resource tracking rows are written to the database

**Acceptance Criteria:**
- RBAC deployments experience no Kessel-related side effects on any resource creation path
- No network calls, no database writes, no log entries related to Kessel sync

---

### UT-KESSEL-RR-002: New resources become authorized through Kessel after reporting

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When a new OCP cluster is registered, users with appropriate role bindings must be able to see its cost data -- this requires the resource to be reported to Kessel with correct representations |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects.update_or_create")` returning `(mock_obj, True)`

**Steps:**
- **Given** a ReBAC deployment where a new OCP cluster `uuid-1` is registered for org `org123`
- **When** the resource reporter processes this new cluster
- **Then** the cluster is reported to Kessel's Inventory API via `ReportResource` with correct representations
- **And** a tracking record is created to confirm successful synchronization

**Acceptance Criteria:**
- The cluster is reported to Kessel Inventory with the correct type, ID, and org association
- The `representations.common` Struct contains `{"workspace_id": "org123"}` for workspace association
- The `representations.metadata` contains `local_resource_id` and `api_href` fields
- The tracking record reflects successful sync, enabling operators to audit Kessel state

---

### UT-KESSEL-RR-003: Resource creation succeeds even when Kessel is temporarily unavailable

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A Kessel outage must not prevent clusters, nodes, or cost models from being created in Postgres -- cost data ingestion must continue |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` where `inventory_stub.ReportResource` raises `grpc.RpcError`
- `@patch("koku_rebac.resource_reporter._track_synced_resource")` to verify it IS called with `synced=False`

**Steps:**
- **Given** a ReBAC deployment where Kessel's Inventory API is temporarily unreachable
- **When** a new OCP cluster is registered
- **Then** the cluster is created in Postgres successfully, and a `KesselSyncedResource` tracking row IS created with `kessel_synced=False` (recording the failed sync for retry)

**Acceptance Criteria:**
- The resource creation in Postgres is not blocked or rolled back
- A `KesselSyncedResource` row IS created with `kessel_synced=False` — tracking always occurs, recording partial failures for retry. The `synced` flag is `(inventory_ok and tuple_ok)`
- A warning is logged so operators can detect the sync failure
- The next pipeline run will retry the gRPC call (idempotent `ReportResource`)

---

### UT-KESSEL-RR-004: Pipeline reruns do not create duplicate resources in Kessel

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | OCP data pipelines reprocess data regularly; duplicate resources in Kessel would cause incorrect authorization results |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects.update_or_create")` returning `(mock_obj, False)` (existing row)

**Steps:**
- **Given** a cluster that was already reported to Kessel in a previous pipeline run
- **When** the pipeline reruns and the resource reporter is invoked for the same cluster
- **Then** the resource is re-reported to Kessel (idempotent) and the tracking record is refreshed, but no duplicate records are created

**Acceptance Criteria:**
- The same resource reported twice results in exactly one tracking record and one Kessel resource
- The sync timestamp is updated to reflect the latest successful sync
- `write_visibility` is NOT set to `IMMEDIATE` for `settings` resource reruns (it is the only type not in `IMMEDIATE_WRITE_TYPES`)
- No errors or duplicate key violations occur

---

### UT-KESSEL-MDL-001: Each resource is tracked exactly once per organization

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If a resource could have multiple tracking rows, sync state becomes ambiguous and operators cannot reliably audit which resources are synchronized |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class with database

**Steps:**
- **Given** a tracking record exists for cluster `uuid-1` in org `org123`
- **When** a duplicate record with the same resource type, ID, and org is inserted directly (bypassing upsert)
- **Then** the database enforces uniqueness and rejects the duplicate

**Acceptance Criteria:**
- The database constraint ensures exactly one tracking row per (resource_type, resource_id, org_id) combination
- This is enforced at the database level, not just application logic, preventing race conditions

---
### UT-SETTINGS-CFG-001: On-prem deployment forces ReBAC authorization regardless of AUTHORIZATION_BACKEND value

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | On-prem deployments must always use Kessel authorization. Allowing an operator to accidentally set `AUTHORIZATION_BACKEND=rbac` would break the deployment since RBAC does not exist on-prem |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(ONPREM=True, AUTHORIZATION_BACKEND="rbac")`

**Steps:**
- **Given** an on-prem deployment where the operator has mistakenly set `AUTHORIZATION_BACKEND=rbac`
- **When** the application resolves the effective authorization backend via `resolve_authorization_backend()`
- **Then** the effective backend is `rebac` (forced), overriding the operator's misconfiguration

**Acceptance Criteria:**
- `ONPREM=True` always forces `AUTHORIZATION_BACKEND` to `rebac` via `resolve_authorization_backend()`
- A warning is logged when the override occurs, alerting the operator to the misconfiguration
- SaaS deployments (`ONPREM=False`) respect the configured value

---

### UT-SETTINGS-CFG-002: Default authorization backend is RBAC for SaaS deployments

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | SaaS deployments that have not explicitly opted into Kessel must continue using RBAC. An incorrect default would break all SaaS cost management authorization |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- No `AUTHORIZATION_BACKEND` environment variable set
- `ONPREM=False`

**Steps:**
- **Given** a SaaS deployment with no explicit `AUTHORIZATION_BACKEND` configuration
- **When** the application reads the authorization backend setting
- **Then** the default is `rbac`, maintaining backward compatibility with the existing SaaS authorization flow

**Acceptance Criteria:**
- The default value is `"rbac"` when the environment variable is not set
- The RBAC service is used for authorization, and no Kessel connections are attempted

---

### UT-SETTINGS-CFG-003: Kessel auth settings are available for service-to-service OAuth2

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Koku authenticates with Kessel via OAuth2 `client_credentials` flow. If any of the required settings (`KESSEL_AUTH_ENABLED`, `KESSEL_AUTH_CLIENT_ID`, `KESSEL_AUTH_CLIENT_SECRET`, `KESSEL_AUTH_OIDC_ISSUER`) are missing, Koku cannot authenticate with Kessel |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** the Django settings module is loaded
- **When** the Kessel auth settings are inspected
- **Then** `KESSEL_AUTH_ENABLED`, `KESSEL_AUTH_CLIENT_ID`, `KESSEL_AUTH_CLIENT_SECRET`, and `KESSEL_AUTH_OIDC_ISSUER` are all accessible from `django.conf.settings`

**Acceptance Criteria:**
- All four settings exist and are readable
- `KESSEL_AUTH_ENABLED` defaults to `ONPREM` (enabled on-prem, disabled on SaaS by default)
- `KESSEL_AUTH_CLIENT_ID` and `KESSEL_AUTH_CLIENT_SECRET` are read from environment variables
- `KESSEL_AUTH_OIDC_ISSUER` is read from environment variables

---

### UT-SETTINGS-CFG-004: RBAC v2 URL is configurable for SaaS workspace resolution

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | SaaS deployments need `RBAC_V2_URL` to reach the RBAC v2 service for workspace resolution. A missing or incorrect URL breaks the `RbacV2Resolver` |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** the Django settings module is loaded with no explicit `RBAC_V2_URL` environment variable
- **When** the `RBAC_V2_URL` setting is inspected
- **Then** it defaults to `"http://localhost:8000"`

**Acceptance Criteria:**
- `RBAC_V2_URL` is readable from `django.conf.settings`
- The default value enables local development without configuration
- The value can be overridden via environment variable for production

---

### UT-SETTINGS-CFG-005: Legacy SpiceDB and Relations API configs are removed

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | `SPICEDB_CONFIG` and `KESSEL_RELATIONS_CONFIG` referenced the old direct-SpiceDB and Relations API connections. If they still exist, code might accidentally connect to the wrong service, bypassing the Inventory API contract |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** the Django settings module is loaded
- **When** `SPICEDB_CONFIG` and `KESSEL_RELATIONS_CONFIG` are accessed
- **Then** they do not exist in settings (raising `AttributeError`)

**Acceptance Criteria:**
- `hasattr(settings, "SPICEDB_CONFIG")` is False
- `hasattr(settings, "KESSEL_RELATIONS_CONFIG")` is False
- No code in `koku_rebac/` references these removed settings

---

### UT-KESSEL-WS-001: On-prem deployments resolve workspace without network calls

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | On-prem deployments have no RBAC v2 service; workspace resolution must work locally by mapping `org_id` directly to `workspace_id` without any network dependency |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(ONPREM=True)`

**Steps:**
- **Given** an on-prem deployment where `ShimResolver` is the active workspace resolver
- **When** `ShimResolver.resolve("org123")` is called
- **Then** the resolver returns `"org123"` directly as the workspace_id

**Acceptance Criteria:**
- `ShimResolver.resolve(org_id)` returns the `org_id` unchanged, enabling authorization checks to target `rbac/workspace:{org_id}`
- No HTTP requests are made to any external service
- The resolver works without any configuration beyond `ONPREM=True`

---

### UT-KESSEL-WS-002: SaaS deployments resolve workspace from RBAC v2 with service credentials

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | SaaS deployments must resolve workspace_id from RBAC v2 using OAuth2 service credentials (not the user's identity), ensuring workspace lookup succeeds regardless of the requesting user's permissions |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.workspace.requests.post")` returning mock token response `{"access_token": "svc-token"}`
- `@patch("koku_rebac.workspace.requests.get")` returning mock workspace response `{"data": [{"id": "ws-uuid-1"}]}`
- `@override_settings(ONPREM=False)`

**Steps:**
- **Given** a SaaS deployment where `RbacV2Resolver` is the active workspace resolver
- **When** `RbacV2Resolver.resolve("org123")` is called
- **Then** the resolver obtains an OAuth2 token via `client_credentials` grant and queries RBAC v2 for the default workspace

**Acceptance Criteria:**
- The resolver uses `client_credentials` grant (not the user's `x-rh-identity`) to authenticate with RBAC v2
- The GET request to RBAC v2 includes the service bearer token in the `Authorization` header
- The resolved workspace_id (`ws-uuid-1`) is returned for use in Kessel authorization checks

---

### UT-KESSEL-WS-003: Workspace resolver caches OAuth2 tokens to avoid per-request token exchanges

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Without token caching, every authorization request triggers a token exchange round-trip to the OIDC issuer, adding latency and load |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.workspace.requests.post")` returning mock token response
- `@patch("koku_rebac.workspace.requests.get")` returning mock workspace response

**Steps:**
- **Given** an `RbacV2Resolver` that has already resolved one workspace (token cached)
- **When** `resolve()` is called a second time for a different org
- **Then** the second call reuses the cached OAuth2 token without issuing a new `client_credentials` POST

**Acceptance Criteria:**
- `requests.post` (token endpoint) is called exactly once across two `resolve()` calls
- `requests.get` (workspace endpoint) is called twice (once per org)
- Both calls succeed with the cached token

---

### UT-KESSEL-WS-004: Missing workspace in RBAC v2 produces a clear error

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | When RBAC v2 returns an empty results array for an org, operators need a clear error identifying the misconfigured org rather than a silent `None` that causes cryptic downstream failures |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.workspace.requests.post")` returning mock token response
- `@patch("koku_rebac.workspace.requests.get")` returning `{"data": []}`

**Steps:**
- **Given** an org_id that has no default workspace configured in RBAC v2
- **When** `RbacV2Resolver.resolve("org-no-ws")` is called
- **Then** the resolver raises `ValueError` with the org_id included in the message

**Acceptance Criteria:**
- The error message includes `"org-no-ws"` so operators can identify which org is misconfigured
- The error is raised immediately rather than returning `None` or an empty string
- The caller (access provider) can catch this and return an appropriate HTTP error

---

### UT-KESSEL-WS-005: Workspace resolver factory dispatches based on ONPREM flag

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | The factory must return the correct resolver implementation based on the deployment type, ensuring no code changes are needed at call sites when switching between on-prem and SaaS |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(ONPREM=True)` and `@override_settings(ONPREM=False)` for separate sub-tests

**Steps:**
- **Given** an on-prem deployment (`ONPREM=True`)
- **When** `get_workspace_resolver()` is called
- **Then** the factory returns a `ShimResolver` instance
- **Given** a SaaS deployment (`ONPREM=False`)
- **When** `get_workspace_resolver()` is called
- **Then** the factory returns an `RbacV2Resolver` instance

**Acceptance Criteria:**
- On-prem deployments get `ShimResolver` (no network dependency)
- SaaS deployments get `RbacV2Resolver` (queries RBAC v2 with OAuth2)
- The factory is deterministic and idempotent

---

### UT-KESSEL-WS-006: RBAC v2 API failure produces an actionable error

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | When the RBAC v2 workspace GET request fails (network error, 500), operators need actionable context to diagnose the issue rather than a raw exception |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.workspace.requests.post")` returning mock token response
- `@patch("koku_rebac.workspace.requests.get")` raising `requests.ConnectionError`

**Steps:**
- **Given** the RBAC v2 service is unreachable
- **When** `RbacV2Resolver.resolve("org123")` is called
- **Then** the HTTP error propagates with enough context for operators to diagnose

**Acceptance Criteria:**
- The `requests.ConnectionError` or `HTTPError` propagates to the caller
- The error includes the RBAC v2 URL that failed, enabling operators to check network connectivity
- The resolver does not silently return a default value

---

### UT-KESSEL-WS-007: OAuth2 token endpoint failure produces an actionable error

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | When the token POST fails (401 bad credentials, network error), operators need to know the token endpoint failed, not the workspace endpoint |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.workspace.requests.post")` raising `requests.HTTPError` (401)

**Steps:**
- **Given** the OAuth2 token endpoint rejects the client credentials (e.g., misconfigured `KESSEL_AUTH_CLIENT_SECRET`)
- **When** `RbacV2Resolver.resolve("org123")` is called
- **Then** the HTTP error from the token endpoint propagates

**Acceptance Criteria:**
- The `HTTPError` from the token POST propagates to the caller
- Operators can distinguish a token endpoint failure from a workspace endpoint failure
- No workspace GET request is attempted when the token request fails

---
### UT-KESSEL-AP-008: Read operations use `_view` compound permission, not raw `_read`

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The `_view` compound permission encapsulates `_read`, `_all`, `all_read`, `all_all`, and `all_all_all` wildcards. Using raw `_read` would bypass wildcard role grants, silently denying access to users with admin or global roles |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.Check`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user whose role grants `cost_management_aws_account_all` (captured by `_view` but not by raw `_read`)
- **When** `KesselAccessProvider` resolves the user's read access for `aws.account`
- **Then** the Check request uses permission `cost_management_aws_account_view`, not `cost_management_aws_account_read`

**Acceptance Criteria:**
- The permission string passed to `inventory_stub.Check` ends with `_view` for all read operations
- Users with `_all`, `all_read`, `all_all`, or `all_all_all` wildcards are granted read access through the compound permission
- No read authorization check uses raw `_read` as the permission name

---

### UT-KESSEL-AP-009: Write operations use `_edit` compound permission, not raw `_write`

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The `_edit` compound permission encapsulates `_write`, `_all`, `all_write`, `all_all`, and `all_all_all` wildcards. Using raw `_write` would bypass wildcard role grants for write-capable types (cost_model, settings) |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.Check`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user whose role grants `cost_management_cost_model_all` (captured by `_edit` but not by raw `_write`)
- **When** `KesselAccessProvider` resolves the user's write access for `cost_model`
- **Then** the Check request uses permission `cost_management_cost_model_edit`, not `cost_management_cost_model_write`

**Acceptance Criteria:**
- The permission string passed to `inventory_stub.Check` ends with `_edit` for all write operations
- Write checks are only performed for `cost_model` and `settings` (the only writable types)

---

### UT-KESSEL-AP-010: Write permission automatically grants read access (RBAC v1 parity)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | RBAC v1's `_update_access_obj()` grants read access when write is granted. If Kessel breaks this parity, users who can edit cost models cannot view them, which is nonsensical |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` where `inventory_stub.Check` returns `ALLOWED_TRUE` for `cost_model` `_edit`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user with write access to cost models (Check for `_edit` returns ALLOWED)
- **When** `KesselAccessProvider` resolves the user's access
- **Then** the access dict sets both `write: ["*"]` and `read: ["*"]` for `cost_model`

**Acceptance Criteria:**
- When `_edit` Check returns ALLOWED, the access dict includes `read: ["*"]` for that type (write grants read)
- This matches RBAC v1's behavior where `write` permission implies `read`
- The read Check is still performed; write-grants-read is additive (if read Check DENIED but write Check ALLOWED, read is still granted)

---

### UT-KESSEL-AP-011: Authorization checks target `rbac/workspace`, not `rbac/tenant`

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The `rbac/workspace` model enables inheritance via `t_binding` and `t_parent` relations. Targeting `rbac/tenant` would bypass workspace-level permission propagation, breaking the authorization model |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.Check`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning `ShimResolver` that resolves to `"org123"`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user in org `org123`
- **When** `KesselAccessProvider` issues a Check request
- **Then** the request's `object.resource_type` is `"workspace"` and `resource_id` is `"org123"` (the resolved workspace_id)

**Acceptance Criteria:**
- Every Check request targets `rbac/workspace` as the resource type
- The `resource_id` is the value returned by the workspace resolver (not hardcoded or derived differently)
- No Check request targets `rbac/tenant`

---

### UT-KESSEL-AP-012: Subject uses `user_id` from identity header, not username

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Kessel principals are identified by `user_id` (from Keycloak JWT `sub` claim via Envoy Lua). Using `username` would create a mismatch with Kessel's principal format, causing all authorization checks to fail |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.Check`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- Mock user with `user_id="12345"` and `username="alice"`

**Steps:**
- **Given** a user with `user_id="12345"` in the identity header
- **When** `KesselAccessProvider` issues a Check request
- **Then** the subject reference uses `"redhat/12345"`, not `"redhat/alice"`

**Acceptance Criteria:**
- The Check request's subject `resource_id` is derived from `user.user_id`
- The subject `resource_type` uses the `redhat` namespace prefix
- `user.username` is NOT used when `user_id` is available

---

### UT-KESSEL-AP-013: Missing `user_id` falls back to username

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | Legacy identity headers may not include `user_id`. Graceful degradation to `username` ensures authorization works during migration periods without breaking existing users |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.Check`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- Mock user with `user_id=None` and `username="alice"`

**Steps:**
- **Given** a user with `user_id=None` (legacy identity format) and `username="alice"`
- **When** `KesselAccessProvider` issues a Check request
- **Then** the subject reference falls back to `"redhat/alice"`

**Acceptance Criteria:**
- When `user.user_id` is `None`, the provider uses `user.username` as the subject identifier
- The authorization check still succeeds (no `None` or empty string in the subject)
- This is a graceful degradation, not the primary path

---

### UT-KESSEL-AP-014: OCP types use StreamedListObjects returning specific resource IDs

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP resources (cluster, node, project) require per-resource authorization -- the query layer needs specific resource IDs to filter cost data. Check (boolean) cannot provide this; StreamedListObjects returns the list of accessible resource IDs |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` where `inventory_stub.StreamedListObjects` returns `["cluster-1", "cluster-2"]` for `openshift_cluster`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user with access to 2 OCP clusters
- **When** `KesselAccessProvider` resolves OCP cluster access
- **Then** `StreamedListObjects` (not Check) is used, and the access dict contains the specific cluster IDs `["cluster-1", "cluster-2"]`

**Acceptance Criteria:**
- `openshift.cluster`, `openshift.node`, and `openshift.project` all use `StreamedListObjects`
- The returned resource IDs are placed directly into the access dict (no wildcard substitution)
- Non-OCP types (aws.account, cost_model, etc.) use Check, not StreamedListObjects

---

### UT-KESSEL-AP-015: StreamedListObjects request targets the correct Kessel resource type

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If the StreamedListObjects request uses the wrong resource type or reporter type, Kessel returns an empty list and users silently lose access to all OCP resources |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` with mock `inventory_stub.StreamedListObjects`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user requesting access to OCP clusters
- **When** `KesselAccessProvider` builds the `StreamedListObjectsRequest`
- **Then** the request's `RepresentationType.resource_type` is `"openshift_cluster"` and `reporter_type` is `"cost_management"`

**Acceptance Criteria:**
- The `resource_type` in the request matches the Kessel naming convention (underscore, no namespace prefix)
- The `reporter_type` is `"cost_management"`, matching the reporter used in `ReportResource`
- Each OCP type maps to the correct Kessel resource type: `openshift_cluster`, `openshift_node`, `openshift_project`

---

### UT-KESSEL-AP-016: OCP inheritance is enforced by the schema, not application code

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Moving OCP inheritance (cluster -> node -> project cascade) from application code to the ZED schema eliminates a class of bugs where application logic diverges from the authorization model |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- Inspect `koku_rebac.access_provider` module

**Steps:**
- **Given** the access provider module after the Inventory API v1beta2 migration
- **When** the module source is inspected
- **Then** no `_apply_ocp_inheritance()` function or equivalent cascade logic exists in the access provider

**Acceptance Criteria:**
- The access provider does NOT contain any function that modifies OCP access based on cluster access (no cascade logic)
- Cluster access granting node/project access is handled entirely by the ZED schema's permission formulas (`t_workspace->` relation)
- The access dict for OCP types contains only the IDs returned by StreamedListObjects, with no application-level expansion

---

### UT-KESSEL-AP-017: StreamedListObjects failure for one OCP type does not block other types

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A single Kessel hiccup for one resource type must not deny all access — only the affected type should be degraded |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` where `inventory_stub.StreamedListObjects` raises `grpc.RpcError` for `openshift_cluster` but succeeds for `openshift_node` and `openshift_project`; all workspace `Check` calls return DENIED (to force StreamedListObjects fallback)
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** Kessel returns a gRPC error for `openshift_cluster` StreamedListObjects but succeeds for other types
- **When** `KesselAccessProvider` resolves the user's access
- **Then** the provider catches the exception for `openshift_cluster` (returns `[]`) and continues resolving other types normally (fail-open per-type, consistent with AP-003)

**Acceptance Criteria:**
- The exception for `openshift_cluster` is caught internally (logged with `LOG.exception`), not propagated
- `access["openshift.cluster"]["read"]` is `[]` (no access for the failed type)
- Other types (`openshift.node`, `openshift.project`) contain the IDs returned by their successful StreamedListObjects calls
- The middleware returns HTTP 200 (not 424) with a valid access dict

---
### UT-KESSEL-RR-006: OCP resources are reported with `write_visibility=IMMEDIATE`

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP resources must be immediately authorizable after reporting. Without `IMMEDIATE`, a newly reported cluster is invisible to StreamedListObjects until the Kessel eventing pipeline processes it asynchronously, creating a window where authorized users cannot see their cluster |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment where a new OCP cluster is being reported
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the `ReportResourceRequest` includes `write_visibility=IMMEDIATE`

**Acceptance Criteria:**
- `openshift_cluster`, `openshift_node`, and `openshift_project` all set `write_visibility=IMMEDIATE`
- The IMMEDIATE flag is set on the gRPC request, enabling read-your-writes consistency in Kessel
- This requires Kessel-side Kafka + Debezium infrastructure for production use

---

### UT-KESSEL-RR-007: Settings resource uses default write visibility (only type excluded from IMMEDIATE)

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | The `settings` sentinel is a capability check, not a per-resource concept — it does not need immediate consistency. All other 10 types in `IMMEDIATE_WRITE_TYPES` use IMMEDIATE |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment where a settings sentinel is being reported
- **When** `on_resource_created("settings", "settings-org123", "org123")` is called
- **Then** the `ReportResourceRequest` does NOT set `write_visibility=IMMEDIATE`

**Acceptance Criteria:**
- `settings` is the ONLY resource type that does not set `write_visibility=IMMEDIATE`
- All other 10 types (`integration`, `openshift_cluster`, `openshift_node`, `openshift_project`, `aws_account`, `aws_organizational_unit`, `gcp_account`, `gcp_project`, `azure_subscription_guid`, `cost_model`) DO set IMMEDIATE
- The default write visibility is used for settings, reducing Kessel infrastructure overhead for this one type

---

### UT-KESSEL-RR-008: Every resource report includes workspace_id in representations

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | The `workspace_id` in `representations.common` enables Kessel to auto-create the `#t_workspace@rbac/workspace` parent tuple. Without it, the resource exists in Kessel but has no workspace association, breaking authorization inheritance |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment where any resource is being reported for org `org123`
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the `ReportResourceRequest.representations.common` Struct contains `{"workspace_id": "org123"}`

**Acceptance Criteria:**
- Every resource type includes `workspace_id` in `representations.common`
- The `workspace_id` matches the org_id passed to the reporter
- Kessel uses this field to auto-create the parent tuple linking the resource to `rbac/workspace:{org_id}`

---

### UT-KESSEL-RR-009: Every resource report includes required metadata fields

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Kessel Inventory API validation requires `local_resource_id` and `api_href` in the representations metadata. Without these fields, the `ReportResource` call is rejected by the Inventory API |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment where a resource is being reported
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the `ReportResourceRequest.representations.metadata` contains `local_resource_id` and `api_href`

**Acceptance Criteria:**
- `local_resource_id` is populated with the resource's ID (e.g., `"uuid-1"`)
- `api_href` is populated with a valid API path for the resource
- Both fields are present for every resource type, satisfying Kessel Inventory API validation

---

### UT-KESSEL-RR-010: `_create_resource_tuples` builds correct Relations API POST body

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The Relations API POST body must exactly match the SpiceDB tuple format -- wrong namespace, relation, or subject shape silently creates an unusable tuple, leaving resources invisible to authorized users |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.post")`

**Steps:**
- **Given** a ReBAC deployment
- **When** `_create_resource_tuples("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the POST body contains `resource_namespace=cost_management`, `resource_type=openshift_cluster`, `resource_id=uuid-1`, `relation=t_workspace`, and subject referencing workspace `org123`

**Acceptance Criteria:**
- POST is sent to `{KESSEL_RELATIONS_URL}{KESSEL_TUPLES_PATH}`
- Body includes all five required tuple fields
- Subject references `rbac/workspace` namespace with the org_id as subject_id

---

### UT-KESSEL-RR-011: `_create_resource_tuples` returns False on HTTP error

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A non-2xx response from the Relations API must not crash the caller -- tuple creation failures are logged and retried on the next pipeline run, not propagated |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.post")` returning `status_code=500`

**Steps:**
- **Given** the Relations API returns HTTP 500
- **When** `_create_resource_tuples("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the function returns `False` and logs a warning

**Acceptance Criteria:**
- Return value is `False`
- No exception propagates to the caller
- A warning-level log message includes resource_type, resource_id, and status code

---

### UT-KESSEL-RR-012: `_create_resource_tuples` returns False on network exception

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Network failures (DNS, timeout, connection refused) must not block data ingestion -- the tuple will be created on the next pipeline rerun |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.post", side_effect=requests.ConnectionError)`

**Steps:**
- **Given** the Relations API is unreachable
- **When** `_create_resource_tuples("openshift_cluster", "uuid-1", "org123")` is called
- **Then** the function returns `False` and logs a warning with `exc_info=True`

**Acceptance Criteria:**
- Return value is `False`
- No exception propagates
- Log includes the connection error traceback

---

### UT-KESSEL-RR-013: `on_resource_created` orchestrates both Inventory and Relations phases

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Resource creation must perform BOTH phases: metadata to Inventory API (ReportResource) and t_workspace tuple to Relations API. Missing either phase leaves resources either untrackable or invisible |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `True`
- `@patch("koku_rebac.resource_reporter._track_synced_resource")`

**Steps:**
- **Given** a ReBAC deployment with both Kessel APIs available
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** `ReportResource` is called on the Inventory stub AND `_create_resource_tuples` is called with the same resource_type, resource_id, and org_id

**Acceptance Criteria:**
- `client.inventory_stub.ReportResource` is called exactly once
- `_create_resource_tuples` is called exactly once with `("openshift_cluster", "uuid-1", "org123")`
- `_track_synced_resource` is called after both phases complete

---

### UT-KESSEL-RR-014: Tuple creation failure does not prevent tracking row creation

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If the Relations API is temporarily down but Inventory API succeeds, the resource metadata is persisted. The tracking row must still be created so that the tuple can be reconciled on the next pipeline run |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `False`
- `@patch("koku_rebac.resource_reporter._track_synced_resource")`

**Steps:**
- **Given** `ReportResource` succeeds but `_create_resource_tuples` returns `False`
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** `_track_synced_resource` is still called (the resource exists in Inventory and must be tracked)

**Acceptance Criteria:**
- The tracking row is created despite tuple creation failure
- No exception propagates to the caller

---

### UT-KESSEL-RR-015: ReportResource failure still runs tuple creation and tracking with synced=False

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Both phases always run regardless of individual failures. If Inventory fails but Relations succeeds, the SpiceDB tuple exists and the resource is partially discoverable. Tracking records `synced=False` so the next pipeline cycle retries the Inventory phase. This is a deliberate design choice — independent best-effort phases |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client raising `grpc.RpcError` on `ReportResource`
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `True`

**Steps:**
- **Given** `ReportResource` raises a gRPC error (setting `inventory_ok=False`)
- **When** `on_resource_created("openshift_cluster", "uuid-1", "org123")` is called
- **Then** `_create_resource_tuples` IS called (proceeds despite Inventory failure), and `_track_synced_resource` IS called with `synced=False` (because `inventory_ok=False`)

**Acceptance Criteria:**
- `_create_resource_tuples` call count is 1 (always runs)
- `_track_synced_resource` call count is 1 with `synced=False`
- The gRPC error is logged but not propagated
- The tracking row enables retry on the next pipeline cycle

---

### UT-KESSEL-RR-016: `_create_resource_tuples` is idempotent on duplicate tuple

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | Pipeline reruns may call `on_resource_created` for a resource that already has a t_workspace tuple. The Relations API must accept or gracefully handle the duplicate without creating a second tuple |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.post")` returning `status_code=200` or `status_code=409`

**Steps:**
- **Given** a t_workspace tuple already exists for a resource
- **When** `_create_resource_tuples("openshift_cluster", "uuid-1", "org123")` is called again
- **Then** the function returns `True` (either 200 OK or 409 Conflict is treated as success)

**Acceptance Criteria:**
- Both HTTP 200 and 409 responses result in `True`
- No error is logged for duplicate tuples
- The function is safe for repeated invocation

---

### UT-KESSEL-RR-017: `_build_delete_request` constructs correct DeleteResourceRequest

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The DeleteResourceRequest must include the correct ResourceReference and ReporterReference -- wrong values cause a NOT_FOUND from Kessel Inventory, leaving orphaned metadata |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **When** `_build_delete_request("openshift_cluster", "uuid-1")` is called
- **Then** the returned `DeleteResourceRequest` has `reference.resource_type == "openshift_cluster"`, `reference.resource_id == "uuid-1"`, `reference.reporter.type == "cost_management"`, and `reference.reporter.instance_id == "uuid-1"`

**Acceptance Criteria:**
- All four fields in the request match the expected values
- The request is a valid `DeleteResourceRequest` protobuf message

---

### UT-KESSEL-RR-018: `_delete_from_kessel` returns True on successful DeleteResource

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Successful Inventory API deletion must signal success to the caller so the cleanup pipeline can proceed to the tuple deletion phase |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- Mock Kessel client with `inventory_stub.DeleteResource` returning successfully

**Steps:**
- **Given** a Kessel client whose `DeleteResource` succeeds
- **When** `_delete_from_kessel(client, "openshift_cluster", "uuid-1")` is called
- **Then** the function returns `True`

**Acceptance Criteria:**
- Return value is `True`
- `DeleteResource` is called exactly once with the correct request

---

### UT-KESSEL-RR-019: `_delete_from_kessel` returns False and logs warning on gRPC error

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Inventory API failures during cleanup must not crash the pipeline -- the failure is logged and the caller can continue with best-effort tuple deletion |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- Mock Kessel client with `inventory_stub.DeleteResource` raising `grpc.RpcError`

**Steps:**
- **Given** a Kessel client whose `DeleteResource` raises `grpc.RpcError`
- **When** `_delete_from_kessel(client, "openshift_cluster", "uuid-1")` is called
- **Then** the function returns `False` and a warning is logged

**Acceptance Criteria:**
- Return value is `False`
- No exception propagates
- Warning log includes resource_type and resource_id

---

### UT-KESSEL-RR-020: `_delete_resource_tuples` constructs correct Relations API DELETE with filter params

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The Relations API DELETE must include all four filter parameters -- missing any one causes either a no-op (tuple survives) or over-broad deletion (wrong tuples removed) |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.delete")` returning `status_code=200`

**Steps:**
- **When** `_delete_resource_tuples("openshift_cluster", "uuid-1")` is called
- **Then** the DELETE request is sent to `http://localhost:8000/api/authz/v1beta1/tuples` with params `filter.resource_namespace=cost_management`, `filter.resource_type=openshift_cluster`, `filter.resource_id=uuid-1`, `filter.relation=t_workspace`

**Acceptance Criteria:**
- All four filter params are present in the request
- The URL matches `{KESSEL_RELATIONS_URL}{KESSEL_TUPLES_PATH}`
- Return value is `True`

---

### UT-KESSEL-RR-021: `_delete_resource_tuples` returns False on HTTP error

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A non-OK response from the Relations API must not crash cleanup -- the failure is logged and the tracking row is still removed to avoid infinite retry loops |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.delete")` returning `status_code=500`

**Steps:**
- **Given** the Relations API returns HTTP 500
- **When** `_delete_resource_tuples("openshift_cluster", "uuid-1")` is called
- **Then** the function returns `False` and logs a warning with the status code

**Acceptance Criteria:**
- Return value is `False`
- No exception propagates
- Warning log includes resource_type, resource_id, and status code

---

### UT-KESSEL-RR-022: `_delete_resource_tuples` returns False on network exception

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Network failures during tuple deletion must not block the cleanup pipeline -- the resource tracking row is still removed |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(KESSEL_RELATIONS_URL="http://localhost:8000", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")`
- `@patch("koku_rebac.resource_reporter.http_requests.delete", side_effect=Exception("connection refused"))`

**Steps:**
- **Given** the Relations API is unreachable
- **When** `_delete_resource_tuples("openshift_cluster", "uuid-1")` is called
- **Then** the function returns `False` and logs a warning with `exc_info=True`

**Acceptance Criteria:**
- Return value is `False`
- No exception propagates
- Log includes the exception traceback

---

### UT-KESSEL-RR-023: `on_resource_deleted` performs full two-phase cleanup

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When cost data is purged due to retention expiry, both Kessel Inventory metadata AND the SpiceDB t_workspace tuple must be removed. Leaving either behind causes stale data in Inventory or phantom resource visibility |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._delete_resource_tuples")` returning `True`
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects")`

**Steps:**
- **Given** a ReBAC deployment with a tracked resource
- **When** `on_resource_deleted("openshift_cluster", "uuid-1", "org123")` is called
- **Then** `_delete_from_kessel` is called (via `client.inventory_stub.DeleteResource`), `_delete_resource_tuples` is called with `("openshift_cluster", "uuid-1")`, and the `KesselSyncedResource` tracking row is deleted

**Acceptance Criteria:**
- `DeleteResource` is called exactly once
- `_delete_resource_tuples` is called exactly once
- `KesselSyncedResource.objects.filter(...).delete()` is called
- When `AUTHORIZATION_BACKEND="rbac"`, none of the above occur (no-op)

---

### UT-KESSEL-RR-024: `cleanup_orphaned_kessel_resources` processes all tracked resources for the entire org

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | After a provider is deleted and its data expires, Kessel resources must be cleaned up. Missing any resource leaves orphaned tuples that grant phantom access or pollute the SpiceDB graph |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._delete_resource_tuples")` returning `True`
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects")` with queryset returning 3 tracked entries
- `@patch("api.models.Provider.objects")` with `filter(...).exists()` returning `False`

**Steps:**
- **Given** a provider `prov-uuid` no longer exists in the database and 3 `KesselSyncedResource` entries are tracked for `org123`
- **When** `cleanup_orphaned_kessel_resources("prov-uuid", "org123")` is called
- **Then** `_delete_from_kessel` and `_delete_resource_tuples` are each called 3 times (once per entry), each entry's `.delete()` is called, and the function returns `3`

**Acceptance Criteria:**
- Returns `3` (number of resources cleaned)
- All 3 resources have both Inventory and Relations cleanup attempted
- Each `KesselSyncedResource` entry is individually deleted
- When provider still exists, returns `0` with no Kessel calls
- When `AUTHORIZATION_BACKEND="rbac"`, returns `0` with no Kessel calls

**Implementation note:** The current code filters tracked resources by `org_id` only (`KesselSyncedResource.objects.filter(org_id=org_id)`), not by `provider_uuid`. This means if multiple providers share the same org, deleting one provider triggers cleanup of ALL tracked resources for the org. This is acceptable for on-prem (typically one provider per org) but would need refinement for multi-provider scenarios.

---


### Retired UT Scenarios

Retired scenarios were removed during the Inventory API v1beta2 migration.

| ID | Title | Reason |
|----|-------|--------|
| UT-KESSEL-SEED-001 | Role seeding command is safe to run in RBAC environments | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-002 | All 5 SaaS production roles are created in Kessel | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-003 | Cost Administrator role grants access to all cost management resource types | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-004 | Cost OpenShift Viewer role grants only OCP cluster access | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-005 | Every RBAC permission string from SaaS role definitions has a Kessel mapping | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-006 | Air-gapped deployments can seed roles from a local file | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SCHEMA-001 | Helm upgrade hooks do not apply redundant schema changes | `kessel_update_schema.py` deleted; schema management externalized to `kessel-admin.sh` |
| UT-KESSEL-VIEW-001 | Administrators can see available roles for assignment | `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-VIEW-002 | Assigning a role to a user takes effect immediately | `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-VIEW-003 | Revoking a role from a user takes effect immediately | `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SEED-007 | Role seeding command supports dry-run mode for safe validation | `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-SCHEMA-002 | Schema update command applies migrations when version is behind | `kessel_update_schema.py` deleted; schema management externalized to `kessel-admin.sh` |
| UT-KESSEL-VIEW-004 | Administrators can list existing role bindings | `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-001 | Create a group in Kessel | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-002 | List groups from Kessel | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-003 | Delete a group from Kessel | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-004 | Add a principal to a group | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-005 | Remove a principal from a group | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-006 | Adding a member invalidates that member's cache | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-007 | Removing a member invalidates that member's cache | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-008 | Binding a role to a group invalidates all members' caches | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-009 | Unbinding a role from a group invalidates all members' caches | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-010 | Role binding serializer accepts subject_type "group" | `serializers.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-011 | Role binding serializer defaults subject_type to "principal" | `serializers.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-GRP-012 | Group CRUD is hidden when AUTHORIZATION_BACKEND is rbac | `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| UT-KESSEL-AP-007 | OCP inheritance replicates RBAC cascade -- cluster access grants node and project access | `_apply_ocp_inheritance()` removed; OCP inheritance now handled by ZED schema permission formulas |
| UT-KESSEL-RR-005 | Resource type names use Kessel naming convention, not Koku RBAC convention | naming convention validation superseded by UT-KESSEL-AP-004 update (type mapping coverage) |

---

## 3. Tier 2 -- Integration Tests (IT)

---

### IT-MW-AUTH-001: ReBAC deployments authorize users through Kessel, not RBAC

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | On-prem deployments have no RBAC service; every request must be authorized through Kessel or users get errors instead of cost data |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user")` returning mock access dict with 2 clusters (uses `inventory_stub.Check` + `StreamedListObjects` internally)
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- Valid `x-rh-identity` header

**Steps:**
- **Given** an on-prem deployment configured with ReBAC authorization
- **When** a user makes a request to a cost management endpoint
- **Then** the user's permissions are resolved through Kessel (not the RBAC HTTP service) and the user can access their authorized cost data

**Acceptance Criteria:**
- Authorization is resolved through the Kessel gRPC API
- The RBAC HTTP service is not contacted
- The user's request proceeds with the access permissions returned by Kessel

---

### IT-MW-AUTH-002: Kessel authorization results are cached to avoid repeated gRPC calls

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Without caching, every API request triggers up to 12 gRPC calls to Kessel (7 non-OCP Check + 2 write Check + 3 OCP StreamedListObjects); caching reduces this to zero for the TTL period |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user")` returning mock access
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- Valid `x-rh-identity` header

**Steps:**
- **Given** a user making their first request (cache miss)
- **When** the user makes a second request within the cache TTL
- **Then** the second request is served from cache without contacting Kessel, and both requests receive identical authorization data

**Acceptance Criteria:**
- Kessel is contacted exactly once for two requests from the same user
- The cached authorization uses the dedicated Kessel cache (not the RBAC cache) to prevent cross-contamination between backends
- Cache entries are keyed by user and org, ensuring multi-tenant isolation

---

### IT-MW-AUTH-003: Kessel outage degrades gracefully (no data visible, not HTTP 424)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When Kessel is down, users see no data (empty access) rather than crashing. Operators must rely on log monitoring to detect degradation |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` where all gRPC calls raise `Exception`
- Valid `x-rh-identity` header

**Steps:**
- **Given** Kessel's Inventory API is unreachable (all gRPC calls fail)
- **When** a user makes any cost management API request
- **Then** the response is HTTP 200 (or 403 depending on the permission class) with an empty access map — the user sees no data

**Acceptance Criteria:**
- The access dict is structurally valid but contains empty lists for all resource types
- All exceptions are logged with `LOG.exception(...)` for operator visibility
- No HTTP 424 is returned (the current access_provider does not raise `KesselConnectionError`)
- **Note**: The middleware does have a `KesselConnectionError` catch handler that would return HTTP 424, but the current `KesselAccessProvider` never raises it. This test verifies the actual fail-open behavior. A separate test should verify the middleware's 424 handler if `KesselConnectionError` is ever raised explicitly in the future

---

### IT-MW-AUTH-004: Org admins have full access during initial bootstrap before role bindings exist

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | On first deployment, no role bindings exist in Kessel yet. The org admin must be able to log in and set up role bindings for other users |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac", ENHANCED_ORG_ADMIN=True)`
- Valid `x-rh-identity` header with `is_org_admin=True`

**Steps:**
- **Given** a fresh on-prem deployment with `ENHANCED_ORG_ADMIN` enabled and no role bindings in Kessel
- **When** the org admin makes a request to any cost management endpoint
- **Then** the admin has full access to all resources without Kessel being contacted

**Acceptance Criteria:**
- The org admin can access all cost management data and APIs
- Kessel is not contacted (no gRPC calls), avoiding errors from empty role bindings
- Non-admin users in the same org are NOT bypassed -- only org admins get this treatment

---

### IT-MW-AUTH-005: New organizations get a settings resource in Kessel for settings-level permissions

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Settings permissions (e.g., currency configuration) require a settings resource to exist in Kessel; without it, `Check` for settings returns denied and settings access is broken |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.on_resource_created")`
- Valid `x-rh-identity` header with new org_id

**Steps:**
- **Given** a request from a user in an organization that Koku has never seen before
- **When** the middleware creates the new customer record
- **Then** a settings sentinel resource is reported to Kessel for that organization, enabling settings-level permission checks

**Acceptance Criteria:**
- The settings resource is created with type `settings` and ID `settings-{org_id}`
- The customer record is created in Postgres before the Kessel reporting (Postgres is the source of truth)
- If Kessel is temporarily unavailable, the customer creation still succeeds (non-blocking)

---

### IT-API-PB-001: New OCP clusters become visible to authorized users after registration

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | When a new OCP cluster is connected through Sources, users with cluster-level role bindings must see its cost data -- if reporting fails, the cluster is invisible |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.on_resource_created")`
- `baker.make(Sources)` for source setup

**Steps:**
- **Given** a ReBAC deployment where a new OCP source is being registered
- **When** the `ProviderBuilder` creates the provider in Postgres
- **Then** the cluster is reported to Kessel Inventory so that `StreamedListObjects` includes it for authorized users

**Acceptance Criteria:**
- The cluster resource is reported to Kessel with its UUID and organization
- The Postgres provider record is created regardless of Kessel reporting outcome
- Only OCP providers trigger cluster reporting

---

### IT-API-PB-002: ProviderBuilder OCP registration creates both Inventory metadata and workspace tuple

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | The ProviderBuilder is the integration point between Sources and Kessel. It must invoke `on_resource_created` which performs both Inventory reporting AND tuple creation -- a gap in either phase breaks resource visibility |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `True`
- `baker.make(Sources)` for source setup

**Steps:**
- **Given** a ReBAC deployment
- **When** `ProviderBuilder.create_service_provider()` completes for an OCP source
- **Then** `on_resource_created` is called, which invokes both `ReportResource` (Inventory) and `_create_resource_tuples` (Relations)

**Acceptance Criteria:**
- Both API phases are invoked in sequence
- `_create_resource_tuples` receives the cluster UUID as `resource_id` and the org_id
- Postgres provider record is created regardless of tuple creation outcome

---

### IT-MASU-SYNC-001: OCP nodes and projects become authorizable during data ingestion

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Fine-grained access control (e.g., "user can only see project X costs") requires each node and project to be a known resource in Kessel |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.on_resource_created")`
- Test OCP report data with 2 nodes and 3 projects

**Steps:**
- **Given** an OCP cluster report containing nodes `["node-a", "node-b"]` and projects `["ns-1", "ns-2", "ns-3"]`
- **When** the data ingestion pipeline processes the cluster information
- **Then** all 5 resources (2 nodes + 3 projects) are reported to Kessel as individually authorizable resources

**Acceptance Criteria:**
- Each node and project is reported as a discrete Kessel resource with its correct type
- The pipeline completes successfully even if some Kessel reports fail
- Subsequent pipeline runs re-report the same resources without errors (idempotent)

---

### IT-MASU-SYNC-002: OCP sub-resource creation triggers tuple creation for each node and project

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Fine-grained authorization requires each node and project to have its own t_workspace tuple in SpiceDB. Without per-resource tuples, `StreamedListObjects` cannot return node-level or project-level results |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `True`
- Test OCP report data with 2 nodes and 3 projects

**Steps:**
- **Given** an OCP cluster report containing nodes `["node-a", "node-b"]` and projects `["ns-1", "ns-2", "ns-3"]`
- **When** the data ingestion pipeline calls `on_resource_created` for each sub-resource
- **Then** `_create_resource_tuples` is called 5 times (once per node and project) with the correct resource_type and resource_id for each

**Acceptance Criteria:**
- `_create_resource_tuples` call count is 5
- Each call has the correct type (`openshift_node` or `openshift_project`) and resource_id
- Pipeline completes successfully even if some tuple creation calls fail

---

### IT-COSTMODEL-CM-001: New cost models become authorized resources in Kessel

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Cost model read/write permissions require the model to exist in Kessel; without reporting, users with `cost_model:write` cannot discover or modify the model |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.on_resource_created")`
- Valid cost model creation payload

**Steps:**
- **Given** a user with cost model write permissions creating a new cost model
- **When** the cost model is saved to Postgres
- **Then** the model is reported to Kessel Inventory so users with appropriate permissions can discover and modify it

**Acceptance Criteria:**
- The cost model resource is reported with its UUID and organization association
- The model persists in Postgres regardless of Kessel reporting outcome
- After reporting, users with cost model role bindings can find it via `StreamedListObjects`

---
### IT-MW-AUTH-007: ReBAC middleware uses Kessel cache, not RBAC cache

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If ReBAC and RBAC share the same cache, switching backends could serve stale authorization from the wrong source, causing incorrect access decisions |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user")`
- `@override_settings(CACHES={CacheEnum.kessel: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}, CacheEnum.rbac: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})` with separate cache instances

**Steps:**
- **Given** a ReBAC deployment with separate Kessel and RBAC caches configured
- **When** a user's authorization is cached during a request
- **Then** the entry is stored in the Kessel cache only, not the RBAC cache

**Acceptance Criteria:**
- The Kessel cache contains the user's authorization data
- The RBAC cache does NOT contain the user's authorization data
- No cross-contamination between caches

---

### IT-MW-AUTH-008: Cache TTL uses provider-specific value

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If the wrong TTL is used, authorization data may be cached too long (security risk) or too short (performance impact) |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user")`

**Steps:**
- **Given** a ReBAC deployment with a configured cache TTL
- **When** a user's authorization is cached
- **Then** the TTL applied to the cache entry matches the provider's `get_cache_ttl()` return value

**Acceptance Criteria:**
- The cache entry uses the provider-specific TTL, not a hard-coded value
- The Kessel provider's TTL is independent of the RBAC service's TTL

---
### IT-MW-AUTH-010: Non-admin user in ReBAC gets access from Kessel

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Non-admin users must have their access resolved through Kessel, receiving exactly the permissions their role bindings grant |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user")` returning mock access dict with 1 cluster (uses `inventory_stub.Check` with `_view` suffix + `StreamedListObjects` internally)
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning mock `ShimResolver`
- Valid `x-rh-identity` header with `is_org_admin=False`

**Steps:**
- **Given** a non-admin user with a role binding granting access to 1 OCP cluster
- **When** the middleware processes their request
- **Then** the user's access is resolved through Kessel and limited to the 1 authorized cluster

**Acceptance Criteria:**
- Kessel is contacted for authorization (not RBAC)
- The user's access dict contains only the authorized cluster
- The middleware does not bypass authorization for non-admin users

---

### IT-MW-WS-001: Workspace resolution failure during middleware prevents silent fallback

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | If workspace resolution fails silently, the middleware might skip authorization or use an incorrect workspace, leading to either a security hole or a cryptic error downstream |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.workspace.get_workspace_resolver")` returning a resolver that raises `ValueError("no workspace for org-bad")`
- Valid `x-rh-identity` header

**Steps:**
- **Given** a ReBAC deployment where the workspace resolver raises an error for the user's org
- **When** the user makes a request to any cost management endpoint
- **Then** the middleware returns an error response rather than silently granting or denying access

**Acceptance Criteria:**
- The middleware does NOT silently grant full access when workspace resolution fails
- The middleware does NOT silently deny all access when workspace resolution fails
- The error response includes enough context for operators to diagnose the workspace resolution issue
- The response status indicates a dependency failure (not a generic 500)

---
### IT-KESSEL-RR-001: Resource reporter idempotency

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Concurrent pipeline runs must not cause duplicate resource creation failures in Kessel |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter.KesselSyncedResource.objects.update_or_create")`

**Steps:**
- **Given** a cluster resource that has already been reported to Kessel
- **When** the resource reporter is invoked again for the same cluster (e.g., during a pipeline rerun)
- **Then** the reporting completes successfully without errors, and the sync record is refreshed

**Acceptance Criteria:**
- The Kessel Inventory API is called idempotently (re-reporting the same resource succeeds)
- The `KesselSyncedResource` tracking record is updated (not duplicated)
- No `IntegrityError` or duplicate key violations occur

---

### IT-KESSEL-RR-002: `on_resource_deleted` triggers two-phase Kessel cleanup

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When cost data is purged due to retention expiry, both the Inventory metadata AND the SpiceDB t_workspace tuple must be removed. Leaving either behind causes stale Inventory entries or phantom resource visibility in `StreamedListObjects` |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._delete_resource_tuples")` returning `True`
- `KesselSyncedResource` tracking row pre-created via `baker.make(KesselSyncedResource)`

**Steps:**
- **Given** a ReBAC deployment where an OCP cluster was previously reported to Kessel and a `KesselSyncedResource` tracking row exists
- **When** `on_resource_deleted("openshift_cluster", "uuid-1", "org123")` is called (simulating retention expiry)
- **Then** `DeleteResource` is called on the Inventory stub AND `_delete_resource_tuples` is called with `("openshift_cluster", "uuid-1")` AND the `KesselSyncedResource` tracking row is deleted

**Acceptance Criteria:**
- `client.inventory_stub.DeleteResource` is called exactly once with the correct request
- `_delete_resource_tuples` is called exactly once with the correct resource_type and resource_id
- The `KesselSyncedResource` row for this resource is removed from PostgreSQL
- Both phases execute independently (failure of one does not prevent the other)

---

### IT-CLEANUP-001: `cleanup_orphaned_kessel_resources` removes all tracked resources for a deleted provider

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | After a provider is deleted via Sources API and its cost data expires, the cleanup pipeline must remove all associated Kessel resources. Orphaned resources pollute the SpiceDB graph and may grant phantom access |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._delete_resource_tuples")` returning `True`
- 3 `KesselSyncedResource` tracking rows pre-created for the same org_id
- Provider no longer exists in the database

**Steps:**
- **Given** a provider `prov-uuid` was previously deleted and its 3 associated `KesselSyncedResource` entries remain
- **When** `cleanup_orphaned_kessel_resources("prov-uuid", "org123")` is called
- **Then** `_delete_from_kessel` and `_delete_resource_tuples` are each called 3 times (once per tracked resource), each tracking row is deleted, and the function returns `3`

**Acceptance Criteria:**
- Returns `3` (correct count of cleaned resources)
- All 3 resources have both Inventory and Relations cleanup attempted
- All 3 `KesselSyncedResource` tracking rows are removed from PostgreSQL
- If the provider still exists in the database, returns `0` with no Kessel calls

---

### IT-SRC-CREATE-001: POST OCP source triggers Kessel resource creation

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The Sources API is the primary entry point for adding OCP clusters on-prem. Without this hook, new clusters are invisible to Kessel authorization |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("api.provider.provider_builder.on_resource_created")`
- `@patch("api.provider.provider_builder.ProviderSerializer")`

**Steps:**
- **Given** an on-prem deployment with ReBAC enabled
- **When** a new OCP source is created via `ProviderBuilder.create_provider_from_source()`
- **Then** `on_resource_created("openshift_cluster", provider_uuid, org_id)` is called

**Acceptance Criteria:**
- `on_resource_created` is called exactly once with correct resource type, ID, and org_id

---

### IT-SRC-CREATE-003: CMMO source_type_id resolves to OCP provider type

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | CMMO operators use numeric IDs ("1" for OCP) not string names. The mapping must be correct for the Kessel hook to fire |
| Phase | 1 |

**Steps:**
- **When** `get_provider_type("1")` is called
- **Then** it returns `"OCP"`
- **And** unknown IDs return `None`

---

### IT-SRC-CREATE-004: Kessel gRPC failure does not fail source creation

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Kessel outages must not prevent source registration. Resource reporter catches gRPC errors internally |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@patch("api.provider.provider_builder.on_resource_created")` with `side_effect=Exception("unexpected reporter error")`

**Steps:**
- **Given** the resource reporter raises an unexpected error (defensive test -- `on_resource_created` normally catches `grpc.RpcError` internally per DD Section 6.2, but this tests caller resilience against bugs in the reporter)
- **When** an OCP source is created
- **Then** the source creation completes without raising

---

### IT-SRC-CREATE-005: Duplicate OCP source creation is idempotent in Kessel

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Pipeline reruns and retry logic may report the same resource multiple times |
| Phase | 1 |

**Steps:**
- **When** `on_resource_created` is called twice for the same cluster
- **Then** both calls succeed, the Inventory stub is called twice, and no errors are raised

---

### IT-SRC-CREATE-006: Source creation triggers both Inventory and Relations API calls

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | When a new source is created via the Sources API, the resulting `on_resource_created` call must report metadata to Inventory AND create the t_workspace tuple in SpiceDB. Missing the tuple leaves the resource invisible to `StreamedListObjects` |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.get_kessel_client")` with mock client
- `@patch("koku_rebac.resource_reporter._create_resource_tuples")` returning `True`
- `baker.make(Sources)` for source setup

**Steps:**
- **Given** a ReBAC deployment where a new OCP source is being registered
- **When** `create_provider_from_source(source)` completes and triggers `on_resource_created`
- **Then** `ReportResource` is called on the Inventory stub AND `_create_resource_tuples` is called with the cluster's resource_type, resource_id, and org_id

**Acceptance Criteria:**
- `client.inventory_stub.ReportResource` is called exactly once
- `_create_resource_tuples` is called exactly once with the correct arguments
- `KesselSyncedResource` tracking row is created

---

### IT-SRC-RETAIN-001: Source deletion deletes integration from Kessel but preserves OCP resources

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Deleting a source must preserve OCP cluster/node/project Kessel resources so historical cost data remains accessible via ReBAC. However, the `integration` resource (representing the source itself) IS deleted from Kessel since it has no historical data to preserve. Cleanup of OCP resources only occurs when data is purged from PostgreSQL due to retention expiry. |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@patch("koku_rebac.resource_reporter.get_kessel_client")`
- `@patch("koku_rebac.resource_reporter._delete_resource_tuples")`
- `@override_settings(ONPREM=True, AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** an OCP source was previously created and reported to Kessel (integration + openshift_cluster)
- **When** `DestroySourceMixin.destroy()` is called on-prem
- **Then** `on_resource_deleted("integration", source_uuid, org_id)` IS called — the integration resource is removed from Kessel Inventory, its SpiceDB tuples are deleted, and the `KesselSyncedResource` tracking row is removed
- **And** the OCP cluster's `KesselSyncedResource` tracking rows remain in PostgreSQL (no `on_resource_deleted` for OCP types)

---

### IT-SRC-ONPREM-001: ONPREM flag enables Sources CRUD

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | On-prem deployments must have full Sources CRUD; SaaS deployments must remain read-only |
| Phase | 1 |

**Steps:**
- **When** the `sources.api.view` module source is inspected
- **Then** the MIXIN_LIST conditional includes `settings.ONPREM or settings.DEVELOPMENT`

---

### IT-SRC-ONPREM-002: Default Sources API is read-only

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | SaaS must not expose create/update/delete endpoints on the Sources API |
| Phase | 1 |

**Steps:**
- **When** the module is loaded with `ONPREM=False` and `DEVELOPMENT=False`
- **Then** `HTTP_METHOD_LIST` is `["get", "head"]` only

---

### IT-MW-AUTH-012: Access management URLs are no longer registered

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | After externalizing the management plane, the `/access-management/` URL prefix must return 404 in all deployment modes. If stale URL patterns remain, they could expose broken endpoints or confuse administrators |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `APIClient` with valid identity headers

**Steps:**
- **Given** any deployment (both `AUTHORIZATION_BACKEND="rebac"` and `"rbac"`)
- **When** a request is made to `/api/cost-management/v1/access-management/roles/`
- **Then** the response is HTTP 404

**Acceptance Criteria:**
- The `/access-management/` URL prefix returns 404 in both `rebac` and `rbac` modes
- No Kessel management API surface is exposed in any deployment configuration
- The URL patterns for roles, role-bindings, and groups are not registered

---


### Retired IT Scenarios

Retired scenarios were removed during the Inventory API v1beta2 migration.

| ID | Title | Reason |
|----|-------|--------|
| IT-API-URL-001 | Access Management API is available in ReBAC deployments | access management URLs removed; management plane externalized to `kessel-admin.sh` |
| IT-API-URL-002 | Access Management API is hidden in RBAC deployments | access management URLs removed; management plane externalized to `kessel-admin.sh` |
| IT-API-URL-003 | Access Management API returns role data through full DRF cycle | access management URLs removed; management plane externalized to `kessel-admin.sh` |
| IT-API-URL-004 | Role binding creation through full DRF cycle invalidates cache | access management URLs removed; management plane externalized to `kessel-admin.sh` |
| IT-API-URL-005 | Group role binding through full DRF cycle invalidates all members | access management URLs removed; management plane externalized to `kessel-admin.sh` |
| IT-MW-AUTH-009 | Backend switching between RBAC and ReBAC is clean | backend switching test obsolete; no shared views between backends after management plane externalization |
| IT-MW-AUTH-011 | Settings sentinel reported on new customer creation | merged into IT-MW-AUTH-005 (identical coverage) |

---

## 4. Tier 3 -- Contract Tests (CT)

---

### CT-SRC-CREATE-001: OCP resource creation via Kessel Inventory API

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Validates real gRPC round-trip to Kessel Inventory API for resource reporting |
| Phase | 1 |

**Prerequisites:**
- Kessel stack running: `podman compose -f dev/kessel/docker-compose.yml up -d`

**Fixtures:**
- `@override_settings(AUTHORIZATION_BACKEND="rebac", KESSEL_INVENTORY_CONFIG=...)`
- Real Kessel Inventory API at `localhost:9081`

**Steps:**
- **Given** the Kessel Inventory API is running
- **When** `on_resource_created("openshift_cluster", resource_id, org_id)` is called
- **Then** the gRPC call completes without error

---

### CT-SRC-CREATE-002: Settings resource type is accepted by inventory

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Validates that non-cluster resource types (e.g., settings) are accepted by the Kessel Inventory API |
| Phase | 1 |

**Steps:**
- **Given** the Kessel Inventory API is running
- **When** `on_resource_created("settings", resource_id, org_id)` is called
- **Then** the gRPC call completes without error

---

### CT-SRC-CREATE-003: Idempotent inventory reporting

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Validates that re-reporting the same resource does not error at the gRPC level |
| Phase | 1 |

**Steps:**
- **When** `on_resource_created` is called twice for the same resource
- **Then** both calls complete without error

---

### CT-SRC-CREATE-004: RBAC mode skips inventory

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Validates that the no-op guard works correctly in a real environment |
| Phase | 1 |

**Steps:**
- **Given** `AUTHORIZATION_BACKEND="rbac"`
- **When** `on_resource_created` is called
- **Then** no gRPC call is made (function returns immediately)

---
### CT-KESSEL-AP-001: Query layer works identically with both RBAC and Kessel authorization

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | The entire query layer (reports, cost models, settings) was built for RBAC's access dict shape. Kessel must produce structurally identical output or every report endpoint breaks |
| Phase | 2 |

**Fixtures:**
- `TestCase` base class
- `@patch` `RbacService.get_access_for_user` returning a known access dict (with `"*"` wildcards)
- `@patch` `KesselAccessProvider` mock returning equivalent access (explicit IDs instead of `"*"`)

**Steps:**
- **Given** an RBAC deployment where a user has wildcard access `{"openshift.cluster": {"read": ["*"]}, ...}` and a Kessel deployment where the same user has explicit access `{"openshift.cluster": {"read": ["uuid-1"]}, ...}`
- **When** both access dicts are fed to the same `QueryParameters._set_access()` method
- **Then** the query layer processes both without errors, filtering correctly in both cases

**Acceptance Criteria:**
- Both dicts have identical top-level keys (all 10 resource types)
- Both dicts have identical operation keys (`read`, `write`) under each resource type
- Both dicts produce list values (RBAC may have `["*"]`, Kessel always has explicit IDs or empty lists)
- No `KeyError`, `TypeError`, or structural mismatch occurs in the query layer

---

### CT-KESSEL-AP-002: Kessel resource IDs match the database fields that queries filter on

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | If Kessel returns resource IDs that don't match what the database stores (e.g., a name vs a UUID), the query filter will silently return no results for authorized users |
| Phase | 2 |

**Fixtures:**
- `TestCase` base class
- `baker.make(Provider, uuid="cluster-uuid-1")` and related test data

**Steps:**
- **Given** an OCP cluster exists in Postgres with `uuid="cluster-uuid-1"`
- **When** Kessel's `StreamedListObjects` returns `"cluster-uuid-1"` for that user
- **Then** the query layer uses that ID to filter and correctly includes the cluster's cost data in the report

**Acceptance Criteria:**
- For every resource type in the mapping, the ID format returned by Kessel matches the database field used for filtering
- This is validated for OCP clusters (UUID), OCP nodes (name), OCP projects (namespace), AWS accounts (account ID), Azure subscriptions (GUID), GCP projects (project ID), and cost models (UUID)

---

### CT-KESSEL-AP-003: Users with no permissions see the same denial regardless of backend

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | A user denied access must be denied consistently whether the deployment uses RBAC or Kessel -- inconsistent behavior would be a security risk |
| Phase | 2 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** a user with no permissions -- RBAC returns `None` (no ACLs) and Kessel returns the equivalent (all resource lookups empty)
- **When** the user requests any cost management report
- **Then** both deployments deny the request identically

**Acceptance Criteria:**
- Both backends signal "no access" in a way that permission classes handle uniformly
- The user receives the same HTTP status and response body regardless of backend
- No edge case allows access when the other backend would deny it

---


### CT-CLEANUP-001: Full cleanup removes resource from StreamedListObjects

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Validates that the complete Kessel cleanup path (Inventory + Relations) revokes resource discoverability. StreamedListObjects is purely SpiceDB-backed; Inventory API DeleteResource alone does NOT revoke access. |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running: `podman compose -f dev/kessel/docker-compose.yml up -d`

**Fixtures:**
- `KesselFixture.seed_access(workspace, user, {"openshift.cluster": {"read": ["*"]}})`
- `KesselFixture.seed_inventory_resources(workspace, "openshift_cluster", [resource_id])`
- `ReportResource(openshift_cluster, resource_id)` via gRPC Inventory API

**BDD Steps:**
- **Given** an OCP cluster resource exists in Kessel Inventory AND the t_workspace SpiceDB tuple links it to the user's workspace
- **When** StreamedListObjects is called for the user
- **Then** the resource is returned
- **When** the t_workspace SpiceDB tuple is deleted via Relations API AND DeleteResource is called on Inventory API
- **Then** StreamedListObjects no longer returns the resource

**Acceptance Criteria:**
- Before cleanup: StreamedListObjects returns the resource ID
- After cleanup: StreamedListObjects does NOT return the resource ID
- The test demonstrates that both Relations API tuple deletion and Inventory API DeleteResource are required for complete revocation

**Implementation:** `koku_rebac/test/test_contract.py::TestDeleteResourceCleanupContract::test_full_cleanup_removes_from_streamed_list`

---

### CT-CLEANUP-002: DeleteResource for nonexistent resource does not error

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Validates graceful handling when cleaning up resources that have already been removed or never existed in Kessel Inventory |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running

**BDD Steps:**
- **Given** no resource exists in Kessel Inventory with the specified ID
- **When** DeleteResource is called for that nonexistent resource
- **Then** the call completes without raising an unexpected error (NOT_FOUND or OK is acceptable)

**Acceptance Criteria:**
- No unexpected gRPC error is raised
- Cleanup logic can safely be idempotent

**Implementation:** `koku_rebac/test/test_contract.py::TestDeleteResourceCleanupContract::test_delete_nonexistent_resource_does_not_error`

---

### Creation Lifecycle

### CT-CREATION-001: ReportResource + tuple creation makes resource visible via StreamedListObjects

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Proves the core business outcome: when Koku registers a resource through both Inventory API (metadata) and Relations API (t_workspace tuple), an authorized user can discover it via `StreamedListObjects`. This is the happy-path proof that the two-phase creation works against real SpiceDB |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running: `podman compose -f dev/kessel/docker-compose.yml up -d`

**Fixtures:**
- `KesselFixture.seed_access(workspace, user, {"openshift.cluster": {"read": ["*"]}})`
- A role binding granting the test user `openshift_cluster:read` in the workspace

**BDD Steps:**
- **Given** roles are seeded and a user has `openshift_cluster:read` permission in workspace `org123`
- **When** `ReportResource` is called for `openshift_cluster:uuid-1` via gRPC Inventory API AND `_create_resource_tuples` creates the `t_workspace` tuple linking `uuid-1` to workspace `org123` via Relations API
- **Then** `StreamedListObjects` for the user returns `uuid-1` in the result set

**Acceptance Criteria:**
- Before creation: `StreamedListObjects` does not return `uuid-1`
- After both phases: `StreamedListObjects` returns `uuid-1`
- The test uses the actual gRPC and REST Kessel APIs (no mocks)

**Implementation:** `koku_rebac/test/test_contract.py::TestCreationLifecycleContract::test_report_and_tuple_makes_resource_visible`

---

### CT-CREATION-002: Tuple creation is idempotent against live SpiceDB

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Pipeline reruns may create the same tuple multiple times. SpiceDB must not reject or create duplicates -- the tuple must remain exactly one relationship regardless of how many times it is written |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running

**BDD Steps:**
- **Given** a t_workspace tuple already exists for `openshift_cluster:uuid-1` in workspace `org123`
- **When** `_create_resource_tuples("openshift_cluster", "uuid-1", "org123")` is called again via the Relations API
- **Then** the call succeeds (HTTP 200 or 409) and `StreamedListObjects` still returns exactly one instance of `uuid-1`

**Acceptance Criteria:**
- No error is raised on duplicate tuple creation
- `StreamedListObjects` returns the resource exactly once (no duplicates)

**Implementation:** `koku_rebac/test/test_contract.py::TestCreationLifecycleContract::test_tuple_creation_is_idempotent`

---

### CT-CREATION-003: Resource reported to Inventory WITHOUT tuple is NOT visible via StreamedListObjects

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Negative proof: if only Inventory metadata exists but no t_workspace tuple is created, the resource must NOT appear in `StreamedListObjects`. This validates that the tuple is the mechanism that grants visibility -- Inventory metadata alone is insufficient |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running

**Fixtures:**
- `KesselFixture.seed_access(workspace, user, {"openshift.cluster": {"read": ["*"]}})`

**BDD Steps:**
- **Given** roles are seeded and a user has `openshift_cluster:read` permission in workspace `org123`
- **When** `ReportResource` is called for `openshift_cluster:uuid-2` via gRPC Inventory API but NO t_workspace tuple is created
- **Then** `StreamedListObjects` for the user does NOT return `uuid-2`

**Acceptance Criteria:**
- `StreamedListObjects` result set does not contain `uuid-2`
- This proves that Inventory metadata alone does not grant visibility
- The test establishes that the tuple is the sole mechanism controlling `StreamedListObjects` results

**Implementation:** `koku_rebac/test/test_contract.py::TestCreationLifecycleContract::test_inventory_only_resource_is_not_visible`

---

### Full Lifecycle

### CT-LIFECYCLE-001: Full create-then-delete round-trip through Koku code paths

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Validates the complete resource lifecycle against live SpiceDB using Koku's own orchestration functions (`on_resource_created` and `on_resource_deleted`). Unlike CT-CLEANUP-001 which uses raw API calls, this test proves that the Python code correctly creates AND removes both Inventory metadata and SpiceDB tuples |
| Phase | 3 |

**Prerequisites:**
- Kessel stack running: `podman compose -f dev/kessel/docker-compose.yml up -d`

**Fixtures:**
- `KesselFixture.seed_access(workspace, user, {"openshift.cluster": {"read": ["*"]}})`
- A role binding granting the test user `openshift_cluster:read` in the workspace

**BDD Steps:**
- **Given** roles are seeded and a user has `openshift_cluster:read` permission in workspace `org123`
- **When** `on_resource_created("openshift_cluster", "uuid-lifecycle", "org123")` is called (Koku's Python orchestration)
- **Then** `StreamedListObjects` returns `uuid-lifecycle`
- **When** `on_resource_deleted("openshift_cluster", "uuid-lifecycle", "org123")` is called (Koku's Python orchestration)
- **Then** `StreamedListObjects` no longer returns `uuid-lifecycle`

**Acceptance Criteria:**
- After creation: resource is visible via `StreamedListObjects`
- After deletion: resource is NOT visible via `StreamedListObjects`
- Both Inventory metadata and SpiceDB tuple are created during `on_resource_created`
- Both Inventory metadata and SpiceDB tuple are removed during `on_resource_deleted`
- The `KesselSyncedResource` tracking row is created during creation and removed during deletion
- This test exercises Koku's orchestration layer, not raw API calls (distinction from CT-CLEANUP-001)

**Implementation:** `koku_rebac/test/test_contract.py::TestLifecycleContract::test_full_create_then_delete_round_trip`

---

### Retired CT Scenarios

Retired scenarios were removed during the Inventory API v1beta2 migration.

| ID | Title | Reason |
|----|-------|--------|
| CT-REL-001 | CreateTuples round-trip | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-002 | DeleteTuples | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-003 | Upsert is idempotent | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-004 | Group membership tuples | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-005 | Role binding with group subject | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-006 | Seed roles produces expected tuple count | Koku no longer uses Relations API directly; role seeding externalized to `kessel-admin.sh` |
| CT-REL-007 | Schema rejects invalid relation | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-REL-008 | Multiple members in a single group | Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| CT-LOOKUP-001 | Authorized user sees the workspace | LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| CT-LOOKUP-002 | Unauthorized user sees nothing | LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| CT-LOOKUP-003 | Wrong permission returns nothing | LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| CT-LOOKUP-004 | Group-based access resolves transitively | LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |

---

## 5. Tier 4 -- E2E Tests (E2E)

Requires full Kessel stack deployed on OCP: relations-api + inventory-api + SpiceDB + PostgreSQL + Kafka.

---

### E2E-KESSEL-FLOW-001: Authorized user can view cost data through the full Kessel authorization chain

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | This validates the complete production path: roles seeded, resources reported, role binding created, and the user can see exactly the cost data they are authorized for -- proving the entire Kessel integration works end-to-end |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP (relations-api + inventory-api + SpiceDB + PostgreSQL + Kafka)
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- Fresh org with seeded roles

**Steps:**
- **Given** an on-prem deployment where roles have been seeded via `seed-roles.yaml` (applied by Helm hooks)
- **And** an OCP cluster is registered and reported to Kessel Inventory
- **And** the administrator has created a role binding granting `cost-openshift-viewer` to user `test-user`
- **When** `test-user` requests the OCP cost report
- **Then** the response includes cost data for the authorized cluster and no other clusters

**Acceptance Criteria:**
- The entire authorization chain works: seed -> report -> bind -> query
- The user sees cost data only for the cluster their role binding grants access to
- The response matches what a user with equivalent RBAC permissions would see in SaaS

---

### E2E-KESSEL-FLOW-002: Unauthorized user is denied access to cost data

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Authorization must restrict access, not just grant it. A user with no role bindings seeing any cost data is a security failure |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- User `no-access-user` with NO role bindings

**Steps:**
- **Given** an OCP cluster is registered and has cost data
- **And** `no-access-user` has no role bindings in Kessel
- **When** `no-access-user` requests the OCP cost report
- **Then** the user is denied access and sees no cost data

**Acceptance Criteria:**
- The user cannot see any cost data from any cluster
- The denial is the same behavior as an RBAC user with no cost-management roles
- The response does not leak cluster names, IDs, or any metadata about resources the user is not authorized to see

---

### E2E-KESSEL-FLOW-003: Revoking a role binding removes access on the user's next request

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Access revocation must take effect immediately -- delayed revocation means a fired employee or reassigned user retains access beyond the admin's intent |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- User `test-user` with an active role binding that grants OCP cluster access

**Steps:**
- **Given** `test-user` can see cost data for their authorized cluster
- **When** the administrator revokes the role binding via the Access Management API
- **And** `test-user` makes another request immediately after revocation
- **Then** the user can no longer see the cluster's cost data

**Acceptance Criteria:**
- The user's access is revoked within one request cycle (cache invalidated on binding deletion)
- The user's subsequent response matches that of a user with no role bindings
- No stale cached access is served after revocation

---

### E2E-KESSEL-FLOW-004: Data pipeline automatically makes OCP nodes and projects authorizable

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Fine-grained authorization (e.g., "user can see only project X") requires nodes and projects to be discovered and reported to Kessel automatically during data ingestion -- without operator intervention |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"` and an OCP source configured
- Test OCP data ingested through the pipeline

**Steps:**
- **Given** an OCP source is registered and cost data is ingested through the pipeline
- **When** the pipeline completes processing and reports resources to Kessel
- **Then** the OCP nodes and projects from the data are available as authorizable resources in Kessel
- **And** a user with a role binding that includes node-level or project-level access can see cost data filtered to those specific resources

**Acceptance Criteria:**
- Nodes and projects are automatically discovered during data ingestion (no manual registration)
- Each resource is trackable via `KesselSyncedResource` with successful sync status
- A user with project-level access sees costs only for their authorized projects

---

### E2E-KESSEL-FLOW-005: Cost model created via API is immediately queryable by authorized users

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | When an admin creates a cost model, users with cost model read access must see it immediately -- delayed visibility means incorrect cost calculations |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- User with cost model write permission (role binding)

**Steps:**
- **Given** a user with `cost-price-list-administrator` role binding
- **When** the user creates a new cost model via the API
- **Then** the cost model is reported to Kessel and immediately visible in the cost model listing for any user with cost model read access

**Acceptance Criteria:**
- The cost model is created in Postgres and reported to Kessel in the same request
- A different user with `cost_model:read` permission can see the new cost model on their next request
- The cost model resource in Kessel matches the UUID stored in Postgres

---

### E2E-KESSEL-FLOW-006: Complete on-prem bootstrap from zero to fully configured

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | This validates the day-one operator experience: starting from a blank deployment, seeding roles, using the org admin bootstrap to create initial role bindings, then transitioning to fully Kessel-governed authorization |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`, `ENHANCED_ORG_ADMIN=true`
- Fresh org with no role bindings

**Steps:**
- **Given** a brand-new on-prem deployment with `ENHANCED_ORG_ADMIN=true` and roles seeded
- **When** the org admin logs in for the first time
- **Then** the admin has full access to all cost management data (bootstrap bypass)
- **When** the admin creates role bindings for team members via the Access Management API
- **And** `ENHANCED_ORG_ADMIN` is set to `false` and Koku is restarted
- **Then** the org admin's access is now governed by their own Kessel role bindings (not the bootstrap bypass)
- **And** team members have access matching the roles assigned to them

**Acceptance Criteria:**
- Bootstrap phase: org admin has unrestricted access, other users have no access
- Transition phase: admin can create role bindings using the Access Management API
- Post-bootstrap phase: all users (including the admin) are governed solely by their Kessel role bindings
- The transition is seamless with no data loss or access gaps

---

### E2E-KESSEL-FLOW-007: Group-based access provides 1:1 RBAC parity

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Validates that a user who is a member of a Kessel group inherits all cost management permissions granted to that group, matching the SaaS RBAC group model |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- Org admin, two regular users (user-A, user-B), one group (team-alpha)

**Steps:**
- **Given** the org admin creates a group `team-alpha` via the Access Management API
- **And** the admin binds `team-alpha` to the `Cost Administrator` role for workspace `ws-1`
- **And** user-A is added to `team-alpha`
- **And** user-B is **not** a member of any group
- **When** user-A queries `/api/cost-management/v1/reports/openshift/costs/`
- **Then** user-A receives cost data for workspace `ws-1`
- **When** user-B queries the same endpoint
- **Then** user-B receives an empty result set (no permissions)
- **When** user-B is added to `team-alpha`
- **And** user-B queries the same endpoint again
- **Then** user-B now receives cost data for workspace `ws-1`

**Acceptance Criteria:**
- Group membership is transitive: adding a user to a group immediately grants the group's permissions
- Removing a user from a group immediately revokes the group's permissions
- The API response contents match what the user would receive under SaaS RBAC with the same group membership

---

### E2E-KESSEL-FLOW-008: Resource creation with tuple makes cluster visible to authorized users

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Proves the full production chain: when an OCP cluster is registered via Sources API, the data pipeline triggers `on_resource_created` which reports metadata to Inventory AND creates the t_workspace tuple in SpiceDB, making the cluster's cost data visible to authorized users. This is the end-to-end proof that the two-phase creation works |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- Roles seeded and a user with `openshift_cluster:read` role binding for the workspace
- An OCP source ready to be registered

**Steps:**
- **Given** roles are seeded and `test-user` has a role binding granting `openshift_cluster:read` in the workspace
- **And** `test-user` queries `/api/cost-management/v1/reports/openshift/costs/` and receives an empty result (no clusters yet)
- **When** a new OCP source is registered via the Sources API
- **And** the data pipeline processes the source, calling `on_resource_created` which performs both `ReportResource` (Inventory) and `_create_resource_tuples` (Relations)
- **Then** `test-user` queries the same endpoint and receives cost data for the newly registered cluster

**Acceptance Criteria:**
- Before registration: `test-user` sees no cost data
- After registration: `test-user` sees cost data for the new cluster
- The cluster is tracked in `KesselSyncedResource` with `kessel_synced=True`
- `StreamedListObjects` returns the cluster for `test-user`
- The test validates the full chain: Sources API -> `on_resource_created` -> Inventory + Relations -> Cost API query

---

### E2E-KESSEL-FLOW-009: Resource deletion via retention expiry removes cluster visibility

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Proves the full production chain for the delete side: when cost data expires and the cleanup pipeline triggers `on_resource_deleted`, both Inventory metadata and the SpiceDB t_workspace tuple are removed, making the cluster's cost data invisible to previously authorized users. Combined with FLOW-008, this validates the complete resource lifecycle |
| Phase | 2 |

**Fixtures:**
- Full Kessel stack on OCP
- Koku deployed with `AUTHORIZATION_BACKEND="rebac"`
- Roles seeded and a user with `openshift_cluster:read` role binding for the workspace
- An OCP cluster previously registered and visible to the user (FLOW-008 precondition met)

**Steps:**
- **Given** `test-user` can see cost data for an OCP cluster (the cluster was registered, reported to Kessel with Inventory metadata and t_workspace tuple)
- **When** the cluster's cost data expires and `on_resource_deleted("openshift_cluster", cluster_uuid, org_id)` is triggered by the data expiry pipeline (or called directly to simulate retention expiry)
- **Then** `test-user` queries `/api/cost-management/v1/reports/openshift/costs/` and receives an empty result for that cluster
- **And** the `KesselSyncedResource` tracking row for the cluster is removed from PostgreSQL

**Acceptance Criteria:**
- Before deletion: `test-user` sees cost data for the cluster
- After deletion: `test-user` sees no cost data for the cluster (empty result)
- `StreamedListObjects` no longer returns the cluster for `test-user`
- Both Inventory metadata and SpiceDB tuple are removed (two-phase cleanup)
- The `KesselSyncedResource` tracking row is deleted
- The test validates the full chain: data expiry -> `on_resource_deleted` -> Inventory DELETE + Relations DELETE -> Cost API query returns empty

---

### E2E Regression: UI Acceptance Scenarios (s1-s53)

These acceptance tests validate that Koku's API endpoints produce correct HTTP outcomes
when authorization flows through Kessel/SpiceDB. They run against a live Kessel stack
and exercise the full middleware chain end-to-end -- the same code path a production
deployment uses when the UI queries the API.

Test implementation:
[koku_rebac/test/test_e2e_regression.py](../../../koku/koku_rebac/test/test_e2e_regression.py)
(requires `ENABLE_KESSEL_TEST=1` and the local Kessel stack via
`podman compose -f dev/kessel/docker-compose.yml up -d`).

**Common fixtures** shared by all scenarios:
- `TestKesselE2ERegression(IamTestCase)` with `KesselFixture`
- `@override_settings(AUTHORIZATION_BACKEND="rebac", ONPREM=True, DEVELOPMENT=False, ENHANCED_ORG_ADMIN=True)`
- Live Kessel stack via `podman compose -f dev/kessel/docker-compose.yml up -d`
- `DummyCache` (no caching -- every request re-evaluates authorization)

#### Basic access grant/deny (s1-s7)

Verifies that users with Kessel read grants can access the corresponding report and management endpoints, and that users without appropriate permissions receive 403 Forbidden.

---

### E2E-KESSEL-GRANT-s01: AWS read granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with AWS account read access must be able to access AWS cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `aws.account` read access for `*`
- **When** the user requests the AWS cost reports endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-aws-costs` returns HTTP 200

---

### E2E-KESSEL-GRANT-s02: GCP read granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with GCP account read access must be able to access GCP cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `gcp.account` read access for `*`
- **When** the user requests the GCP cost reports endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-gcp-costs` returns HTTP 200

---

### E2E-KESSEL-GRANT-s03: Azure read granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with Azure subscription read access must be able to access Azure cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `azure.subscription_guid` read access for `*`
- **When** the user requests the Azure cost reports endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-azure-costs` returns HTTP 200

---

### E2E-KESSEL-GRANT-s04: Cost model read granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with cost model read access must be able to list cost models |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"read": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `cost_model` read access for `*`
- **When** the user requests the cost models list endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET cost-models-list` returns HTTP 200

---

### E2E-KESSEL-GRANT-s05: Settings read granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with settings read access must be able to view tag settings |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"read": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `settings` read access for `*`
- **When** the user requests the settings-tags endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET settings-tags` returns HTTP 200

---

### E2E-KESSEL-GRANT-s06: No permissions returns 403

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with no Kessel permissions must be denied access to cost reports |
| Phase | 1 |

**Fixtures:**
- Dedicated "denied" user with no Kessel tuples

**Steps:**
- **Given** a user with no Kessel permissions (no tuples seeded)
- **When** the user requests the AWS cost reports endpoint
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-aws-costs` returns HTTP 403

---

### E2E-KESSEL-GRANT-s07: Partial permissions wrong type returns 403

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | AWS-only permissions must not grant access to GCP reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})` (for other user)
- Denied user with no GCP tuples

**Steps:**
- **Given** a denied user with no GCP tuples
- **When** the user requests the GCP cost reports endpoint
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-gcp-costs` returns HTTP 403

---

#### Write grants read (s8, s12)

Verifies that write permission on a resource type implicitly grants read access.

---

### E2E-KESSEL-WRITE-s08: Cost model write grants read

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Write permission on cost_model must implicitly grant read access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"write": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `cost_model` write access (no explicit read)
- **When** the user requests the cost models list endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET cost-models-list` returns HTTP 200

---

#### Org admin bypass (s9)

---

### E2E-KESSEL-ADMIN-s09: Org admin bypass without tuples

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Org admins must get full access without any Kessel tuples (middleware bypass) |
| Phase | 1 |

**Fixtures:**
- Org admin identity header (`is_admin=True`) with no Kessel tuples

**Steps:**
- **Given** an org admin user with no Kessel tuples
- **When** the user requests the AWS cost reports endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-aws-costs` returns HTTP 200

---

#### OCP StreamedListObjects basic (s10-s11)

Verifies that OCP cost reports require both Kessel read grants and seeded OCP resources via StreamedListObjects.

---

### E2E-KESSEL-OCP-s10: OCP cluster resources granted

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with OCP cluster read access and seeded resources must access OpenShift cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["test-cluster-001"])`

**Steps:**
- **Given** a non-admin user with `openshift.cluster` read access and seeded OCP resources
- **When** the user requests the OpenShift cost reports endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-costs` returns HTTP 200

---

### E2E-KESSEL-OCP-s11: No OCP resources returns 403

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with no OCP resources must be denied access to OpenShift cost reports |
| Phase | 1 |

**Fixtures:**
- Denied user with no OCP resources

**Steps:**
- **Given** a user with no OCP resources
- **When** the user requests the OpenShift cost reports endpoint
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-openshift-costs` returns HTTP 403

---

### E2E-KESSEL-WRITE-s12: Settings write grants read

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Write permission on settings must implicitly grant read access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})`

**Steps:**
- **Given** a non-admin user with `settings` write access (no explicit read)
- **When** the user requests the settings-tags endpoint
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET settings-tags` returns HTTP 200

---

#### Provider isolation (s13-s15)

Verifies that access to one provider does NOT bleed into unrelated providers, resource types, or management endpoints.

---

### E2E-KESSEL-ISOLATE-s13: AWS-only denies all other providers

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | AWS-only access must not grant GCP, Azure, OCP, cost_model, or settings access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s13-exclusive", {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with only `aws.account` read access
- **When** the user requests AWS, GCP, Azure, OCP cost reports, cost-models, and settings
- **Then** AWS returns 200; all others return 403

**Acceptance Criteria:**
- `reports-aws-costs` returns HTTP 200
- `reports-gcp-costs`, `reports-azure-costs`, `reports-openshift-costs`, `cost-models-list`, `settings-tags` return HTTP 403

---

### E2E-KESSEL-ISOLATE-s14: OCP-only denies cloud and management

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP-only access must not grant AWS, GCP, Azure, cost_model, or settings access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s14-ocp-only", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s14-cluster"], wait_user="e2e-s14-ocp-only")`

**Steps:**
- **Given** a user with only `openshift.cluster` read access and seeded OCP resources
- **When** the user requests OCP, AWS, GCP, Azure cost reports, cost-models, and settings
- **Then** OCP returns 200; all others return 403

**Acceptance Criteria:**
- `reports-openshift-costs` returns HTTP 200
- `reports-aws-costs`, `reports-gcp-costs`, `reports-azure-costs`, `cost-models-list`, `settings-tags` return HTTP 403

---

### E2E-KESSEL-ISOLATE-s15: Zero permissions denied all endpoints

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with no Kessel permissions must be denied on every report and management endpoint |
| Phase | 1 |

**Fixtures:**
- Denied user with no Kessel permissions

**Steps:**
- **Given** a user with no Kessel permissions
- **When** the user requests all report and management endpoints
- **Then** all endpoints return 403

**Acceptance Criteria:**
- `reports-aws-costs`, `reports-gcp-costs`, `reports-azure-costs`, `reports-openshift-costs`, `cost-models-list`, `settings-tags` all return HTTP 403

---

#### OCP-on-Cloud cross-provider views (s16-s20d)

OCP-on-AWS, OCP-on-Azure, and OCP-on-GCP views require BOTH the cloud provider permission AND OpenShift permission. Both halves of the dual-permission requirement are tested independently. OCP-on-All requires at least one provider type with read access.

---

### E2E-KESSEL-XPROV-s16: OCP + AWS grants OCP-on-AWS reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with both OCP cluster and AWS account access must view OCP-on-AWS cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s16-ocp-aws", {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s16-cluster"], wait_user="e2e-s16-ocp-aws")`

**Steps:**
- **Given** a user with both OCP cluster and AWS account read access
- **When** the user requests `reports-openshift-aws-costs`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-aws-costs` returns HTTP 200

---

### E2E-KESSEL-XPROV-s17: OCP without AWS denies OCP-on-AWS reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-only access (no AWS) must be denied OCP-on-AWS reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s17-ocp-no-aws", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s17-cluster"], wait_user="e2e-s17-ocp-no-aws")`

**Steps:**
- **Given** a user with OCP cluster access but no AWS account access
- **When** the user requests `reports-openshift-aws-costs`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-openshift-aws-costs` returns HTTP 403

---

### E2E-KESSEL-XPROV-s18: OCP + Azure grants OCP-on-Azure reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with both OCP cluster and Azure subscription access must view OCP-on-Azure cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s18-ocp-azure", {"openshift.cluster": {"read": ["*"]}, "azure.subscription_guid": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s18-cluster"], wait_user="e2e-s18-ocp-azure")`

**Steps:**
- **Given** a user with both OCP cluster and Azure subscription read access
- **When** the user requests `reports-openshift-azure-costs`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-azure-costs` returns HTTP 200

---

### E2E-KESSEL-XPROV-s19: OCP without Azure denies OCP-on-Azure reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-only access (no Azure) must be denied OCP-on-Azure reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s19-ocp-no-azure", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s19-cluster"], wait_user="e2e-s19-ocp-no-azure")`

**Steps:**
- **Given** a user with OCP cluster access but no Azure subscription access
- **When** the user requests `reports-openshift-azure-costs`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-openshift-azure-costs` returns HTTP 403

---

### E2E-KESSEL-XPROV-s20: OCP access alone grants OCP-on-All reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-on-All requires at least one provider type with read access; OCP cluster alone is sufficient |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s20-ocp-on-all", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20-cluster"], wait_user="e2e-s20-ocp-on-all")`

**Steps:**
- **Given** a user with OCP cluster read access (no cloud provider access)
- **When** the user requests `reports-openshift-all-costs`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-all-costs` returns HTTP 200

---

### E2E-KESSEL-XPROV-s20b: AWS without OCP denies OCP-on-AWS reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | AWS-only access (no OCP) must be denied OCP-on-AWS reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s20b-aws-no-ocp", {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS account access but no OCP cluster access
- **When** the user requests `reports-openshift-aws-costs`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-openshift-aws-costs` returns HTTP 403

---

### E2E-KESSEL-XPROV-s20c: OCP + GCP grants OCP-on-GCP reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with both OCP cluster and GCP account access must view OCP-on-GCP cost reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s20c-ocp-gcp", {"openshift.cluster": {"read": ["*"]}, "gcp.account": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20c-cluster"], wait_user="e2e-s20c-ocp-gcp")`

**Steps:**
- **Given** a user with both OCP cluster and GCP account read access
- **When** the user requests `reports-openshift-gcp-costs`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-gcp-costs` returns HTTP 200

---

### E2E-KESSEL-XPROV-s20d: OCP without GCP denies OCP-on-GCP reports

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-only access (no GCP) must be denied OCP-on-GCP reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s20d-ocp-no-gcp", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20d-cluster"], wait_user="e2e-s20d-ocp-no-gcp")`

**Steps:**
- **Given** a user with OCP cluster access but no GCP account access
- **When** the user requests `reports-openshift-gcp-costs`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET reports-openshift-gcp-costs` returns HTTP 403

---

#### Query-parameter filtering (s21-s24)

The UI always sends filter parameters (`filter[account]`, `filter[cluster]`, etc.). These must be accepted without breaking authorization.

---

### E2E-KESSEL-FILTER-s21: AWS reports accept filter[account]

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | AWS cost reports must support account-level filtering for users with AWS access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS account read access
- **When** the user requests `reports-aws-costs` with `filter[account]=123456789`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-aws-costs?filter[account]=123456789` returns HTTP 200

---

### E2E-KESSEL-FILTER-s22: OCP reports accept filter[cluster]

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | OCP cost reports must support cluster-level filtering for users with OCP access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s22-filter-cluster"])`

**Steps:**
- **Given** a user with OCP cluster read access and seeded cluster `s22-filter-cluster`
- **When** the user requests `reports-openshift-costs` with `filter[cluster]=s22-filter-cluster`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-costs?filter[cluster]=s22-filter-cluster` returns HTTP 200

---

### E2E-KESSEL-FILTER-s23: Azure reports accept filter[subscription_guid]

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | Azure cost reports must support subscription-level filtering for users with Azure access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})`

**Steps:**
- **Given** a user with Azure subscription read access
- **When** the user requests `reports-azure-costs` with `filter[subscription_guid]=<uuid>`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-azure-costs?filter[subscription_guid]=...` returns HTTP 200

---

### E2E-KESSEL-FILTER-s24: GCP reports accept filter[account]

| Field | Value |
|-------|-------|
| Priority | P2 (Medium) |
| Business Value | GCP cost reports must support account-level filtering for users with GCP access |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with GCP account read access
- **When** the user requests `reports-gcp-costs` with `filter[account]=gcp-acct-1`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-gcp-costs?filter[account]=gcp-acct-1` returns HTTP 200

---

#### Resource-type discovery (s25-s29c)

The UI calls resource-type endpoints to populate filter dropdowns. These must respect Kessel authorization.

---

### E2E-KESSEL-RTYPE-s25: AWS accounts resource type granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with AWS access must be able to list AWS account resource types for filter dropdown population |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS account read access
- **When** the user requests `aws-accounts`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET aws-accounts` returns HTTP 200

---

### E2E-KESSEL-RTYPE-s26: AWS accounts resource type denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without AWS access must not list AWS account resource types |
| Phase | 1 |

**Fixtures:**
- Denied user with no AWS access

**Steps:**
- **Given** a user without AWS account access
- **When** the user requests `aws-accounts`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET aws-accounts` returns HTTP 403

---

### E2E-KESSEL-RTYPE-s27: OpenShift clusters resource type granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with OCP access must be able to list OpenShift cluster resource types |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s27-cluster"])`

**Steps:**
- **Given** a user with OCP cluster read access and seeded cluster `s27-cluster`
- **When** the user requests `openshift-clusters`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET openshift-clusters` returns HTTP 200

---

### E2E-KESSEL-RTYPE-s28: OpenShift clusters resource type denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without OCP access must not list OpenShift cluster resource types |
| Phase | 1 |

**Fixtures:**
- Denied user with no OCP access

**Steps:**
- **Given** a user without OCP cluster access
- **When** the user requests `openshift-clusters`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET openshift-clusters` returns HTTP 403

---

### E2E-KESSEL-RTYPE-s29: Azure subscriptions resource type granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with Azure access must be able to list Azure subscription resource types |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})`

**Steps:**
- **Given** a user with Azure subscription read access
- **When** the user requests `azure-subscription-guids`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET azure-subscription-guids` returns HTTP 200

---

### E2E-KESSEL-RTYPE-s29a: Azure subscriptions resource type denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without Azure access must not list Azure subscription resource types |
| Phase | 1 |

**Fixtures:**
- Denied user with no Azure access

**Steps:**
- **Given** a user without Azure subscription access
- **When** the user requests `azure-subscription-guids`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET azure-subscription-guids` returns HTTP 403

---

### E2E-KESSEL-RTYPE-s29b: GCP accounts resource type granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with GCP access must be able to list GCP account resource types |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with GCP account read access
- **When** the user requests `gcp-accounts`
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET gcp-accounts` returns HTTP 200

---

### E2E-KESSEL-RTYPE-s29c: GCP accounts resource type denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without GCP access must not list GCP account resource types |
| Phase | 1 |

**Fixtures:**
- Denied user with no GCP access

**Steps:**
- **Given** a user without GCP account access
- **When** the user requests `gcp-accounts`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET gcp-accounts` returns HTTP 403

---

#### User-access endpoint (s30-s31)

The UI calls `/user-access/?type=<provider>` to determine which navigation tabs and pages to render. The response must reflect Kessel permissions.

---

### E2E-KESSEL-USERACCESS-s30: User-access reflects AWS permission

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | User-access endpoint must report `data=true` for AWS when the user has AWS permission |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS account read access
- **When** the user requests `user-access` with `type=aws`
- **Then** the response status is 200 OK and `data` is `true`

**Acceptance Criteria:**
- `GET user-access?type=aws` returns HTTP 200
- Response `data` field is `true`

---

### E2E-KESSEL-USERACCESS-s31: User-access denies GCP without permission

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | User-access endpoint must report `data=false` for GCP when the user has no GCP permission |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s31-no-gcp", {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS access but no GCP access
- **When** the user requests `user-access` with `type=gcp`
- **Then** the response status is 200 OK and `data` is `false`

**Acceptance Criteria:**
- `GET user-access?type=gcp` returns HTTP 200
- Response `data` field is `false`

---

#### Forecast endpoints (s32-s35c)

Forecast views follow the same permission model as reports. Cross-provider forecasts (OCP-on-AWS) require both provider permissions.

---

### E2E-KESSEL-FORECAST-s32: AWS cost forecast granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with AWS read access must be able to retrieve AWS cost forecasts |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** a user with AWS account read access
- **When** the user requests AWS cost forecasts
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET aws-cost-forecasts` returns HTTP 200

---

### E2E-KESSEL-FORECAST-s33: AWS cost forecast denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without AWS access must be denied AWS cost forecasts |
| Phase | 1 |

**Fixtures:**
- Denied user with no AWS access

**Steps:**
- **Given** a user without AWS account access
- **When** the user requests AWS cost forecasts
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET aws-cost-forecasts` returns HTTP 403

---

### E2E-KESSEL-FORECAST-s34: OCP-on-AWS forecast requires both OCP and AWS

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-on-AWS forecasts must require both OpenShift and AWS read permissions |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s34-ocp-aws-fc", {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s34-cluster"], wait_user="e2e-s34-ocp-aws-fc")`

**Steps:**
- **Given** a user with both OCP cluster and AWS account read access
- **When** the user requests OCP-on-AWS cost forecasts
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET openshift-aws-cost-forecasts` returns HTTP 200

---

### E2E-KESSEL-FORECAST-s35: OCP-on-AWS forecast denied without AWS

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | OCP-only access (no AWS) must be denied OCP-on-AWS forecasts |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s35-ocp-no-aws-fc", {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s35-cluster"], wait_user="e2e-s35-ocp-no-aws-fc")`

**Steps:**
- **Given** a user with OCP cluster read access but no AWS access
- **When** the user requests OCP-on-AWS cost forecasts
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET openshift-aws-cost-forecasts` returns HTTP 403

---

### E2E-KESSEL-FORECAST-s35b: OpenShift cost forecast granted

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users with OCP access must be able to retrieve OpenShift cost forecasts |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s35b-cluster"])`

**Steps:**
- **Given** a user with OCP cluster read access and seeded OCP resources
- **When** the user requests OpenShift cost forecasts
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET openshift-cost-forecasts` returns HTTP 200

---

### E2E-KESSEL-FORECAST-s35c: OpenShift cost forecast denied

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Users without OCP access must be denied OpenShift cost forecasts |
| Phase | 1 |

**Fixtures:**
- Denied user with no OCP access

**Steps:**
- **Given** a user without OCP cluster access
- **When** the user requests OpenShift cost forecasts
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `GET openshift-cost-forecasts` returns HTTP 403

---

#### Write operations (s36-s40)

The UI performs POST (create cost model) and PUT (enable/disable tags) operations. Authorization for writes is distinct from reads and must be validated through Kessel.

---

### E2E-KESSEL-WRITE-s36: Cost model POST authorized

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with cost_model write access must pass authorization for POST (body validation may return 400) |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"write": ["*"]}})`

**Steps:**
- **Given** a user with cost_model write access
- **When** the user POSTs to cost-models
- **Then** the response is not 403 (may be 400 for body validation)

**Acceptance Criteria:**
- `POST cost-models-list` does not return HTTP 403

---

### E2E-KESSEL-WRITE-s37: Cost model POST denied (read-only)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with cost_model read-only must not create cost models |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s37-cm-readonly", {"cost_model": {"read": ["*"]}})`

**Steps:**
- **Given** a user with cost_model read-only access
- **When** the user POSTs to cost-models
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `POST cost-models-list` returns HTTP 403

---

### E2E-KESSEL-WRITE-s38: Cost model GET and POST denied (no access)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with no cost_model access must be denied both GET and POST |
| Phase | 1 |

**Fixtures:**
- Denied user with no cost_model access

**Steps:**
- **Given** a user with no cost_model access
- **When** the user GETs and POSTs to cost-models
- **Then** both responses are 403 Forbidden

**Acceptance Criteria:**
- `GET cost-models-list` returns HTTP 403
- `POST cost-models-list` returns HTTP 403

---

### E2E-KESSEL-WRITE-s39: Settings PUT authorized

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with settings write access must pass authorization for PUT (may return 400/200) |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})`

**Steps:**
- **Given** a user with settings write access
- **When** the user PUTs to tag-enable
- **Then** the response is not 403

**Acceptance Criteria:**
- `PUT tags-enable` does not return HTTP 403

---

### E2E-KESSEL-WRITE-s40: Settings PUT denied (read-only)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with settings read-only must not update tag-enable settings |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s40-settings-ro", {"settings": {"read": ["*"]}})`

**Steps:**
- **Given** a user with settings read-only access
- **When** the user PUTs to tag-enable
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `PUT tags-enable` returns HTTP 403

---

#### Realistic multi-provider profile (s41)

End-to-end simulation of a realistic user with access to multiple providers, validating the full access surface in one test.

---

### E2E-KESSEL-PROFILE-s41: Realistic multi-provider user

| Field | Value |
|-------|-------|
| Priority | P1 (High) |
| Business Value | Realistic multi-provider access must behave correctly across all report, management, and discovery endpoints |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s41-realistic", {"aws.account": {"read": ["*"]}, "openshift.cluster": {"read": ["*"]}, "settings": {"read": ["*"]}})`
- `seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s41-cluster"], wait_user="e2e-s41-realistic")`

**Steps:**
- **Given** a user with AWS, OCP, and settings read access and seeded OCP resources
- **When** the user accesses all report, management, discovery, and user-access endpoints
- **Then** granted endpoints return 200, denied endpoints return 403, user-access reflects access correctly

**Acceptance Criteria:**
- Granted (200): `reports-aws-costs`, `reports-openshift-costs`, `reports-openshift-aws-costs`, `reports-openshift-all-costs`, `settings-tags`, `aws-accounts`, `openshift-clusters`, `aws-cost-forecasts`
- Denied (403): `reports-gcp-costs`, `reports-azure-costs`, `reports-openshift-azure-costs`, `reports-openshift-gcp-costs`, `cost-models-list`
- `user-access?type=aws` returns `data=true`
- `user-access?type=gcp` returns `data=false`

---

#### Resource-level scoping via StreamedListObjects (s42-s45)

When inventory resources are seeded for specific IDs, Kessel's `StreamedListObjects` returns those IDs instead of granting wildcard access. Views filter data to only those resources.

---

### E2E-KESSEL-SCOPE-s42: OCP specific cluster IDs auth passes

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP users with specific cluster IDs (not wildcard) must access OCP reports via non-wildcard access path |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s42-scoped", {"openshift.cluster": {"read": ["*"]}})`
- `seed_inventory_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s42-cluster-A", "s42-cluster-B"], wait_user="e2e-s42-scoped")`

**Steps:**
- **Given** an OCP user with specific cluster IDs seeded as inventory resources
- **When** the user requests OCP cost reports
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-costs` returns HTTP 200
- StreamedListObjects returns specific IDs, not wildcard

---

### E2E-KESSEL-SCOPE-s43: OCP clusters resource-type filtered by scope

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP clusters resource-type endpoint must return only seeded/authorized cluster IDs |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s43-rt-scoped", {"openshift.cluster": {"read": ["*"]}})`
- `seed_inventory_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s43-cluster-X"], wait_user="e2e-s43-rt-scoped")`

**Steps:**
- **Given** an OCP user with specific cluster scope for `s43-cluster-X`
- **When** the user requests `openshift-clusters`
- **Then** the response is 200 OK and all returned items have cluster ID in `["s43-cluster-X"]`

**Acceptance Criteria:**
- `GET openshift-clusters` returns HTTP 200
- All items in response data have value matching the seeded cluster IDs

---

### E2E-KESSEL-SCOPE-s44: OCP-on-AWS with scoped OCP + AWS wildcard

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP-on-AWS must work when user has specific OCP cluster IDs (StreamedListObjects) + AWS wildcard (Check) |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s44-scoped-xprov", {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}})`
- `seed_inventory_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s44-cluster"], wait_user="e2e-s44-scoped-xprov")`

**Steps:**
- **Given** a user with specific OCP cluster IDs and AWS wildcard access
- **When** the user requests OCP-on-AWS cost reports
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-aws-costs` returns HTTP 200

---

### E2E-KESSEL-SCOPE-s45: OCP single cluster scoping

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Single-resource access list must work end-to-end for OCP reports |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s45-single", {"openshift.cluster": {"read": ["*"]}})`
- `seed_inventory_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s45-only-cluster"], wait_user="e2e-s45-single")`

**Steps:**
- **Given** an OCP user with exactly one cluster seeded
- **When** the user requests OCP cost reports
- **Then** the response status is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-costs` returns HTTP 200

---

#### Sources API and Kessel Inventory persistence (s46-s53)

The on-prem Sources API (`POST /sources/`) replaces `sources-api-go`. OCP source creation must persist to both PostgreSQL and Kessel Inventory. Non-OCP sources must persist only to PostgreSQL.

---

### E2E-KESSEL-SRC-s46: OCP source creates PostgreSQL records

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP source creation must persist Source and Provider rows in PostgreSQL |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})`

**Steps:**
- **Given** a user with settings write access
- **When** the user POSTs an OCP source to `/sources/`
- **Then** the response is 200/201 and Source + Provider rows exist in PostgreSQL

**Acceptance Criteria:**
- `POST sources-list` returns HTTP 200 or 201
- `Sources` row exists with `koku_uuid` set
- `Provider` row exists for the created source

---

### E2E-KESSEL-SRC-s47: OCP source creates Kessel tracking record

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP source creation must create a KesselSyncedResource tracking row for Kessel Inventory |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})`

**Steps:**
- **Given** an OCP source created via Sources API
- **When** Kessel tracking is verified
- **Then** `KesselSyncedResource` exists with `resource_type="openshift_cluster"` and `kessel_synced=True`

**Acceptance Criteria:**
- `KesselSyncedResource` row exists for the created OCP source
- `kessel_synced` is `True`

---

### E2E-KESSEL-SRC-s48: OCP resource discoverable via Kessel

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | OCP resources created via Sources API must be discoverable by Kessel-authorized users via StreamedListObjects |
| Phase | 1 |

**Fixtures:**
- OCP source created via Sources API
- Second user with OCP read access: `seed_access(E2E_WORKSPACE_ID, "e2e-s48-reader", {"openshift.cluster": {"read": ["*"]}})`

**Steps:**
- **Given** an OCP source created via Sources API reports the resource to Kessel Inventory
- **When** a second user with OCP read access requests OCP reports
- **Then** StreamedListObjects discovers the resource and the response is 200 OK

**Acceptance Criteria:**
- `GET reports-openshift-costs` returns HTTP 200 for the second user
- Resource is visible via StreamedListObjects

---

### E2E-KESSEL-SRC-s49: AWS source no Kessel inventory entry

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Non-OCP sources must persist to PostgreSQL only -- no KesselSyncedResource entry |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})`
- `@patch("providers.provider_access.ProviderAccessor.cost_usage_source_ready", return_value=True)`

**Steps:**
- **Given** a user creates an AWS-local source via Sources API
- **When** Kessel tracking is verified
- **Then** no `KesselSyncedResource` exists; PostgreSQL records exist

**Acceptance Criteria:**
- `POST sources-list` returns HTTP 200 or 201
- Source and Provider rows exist in PostgreSQL
- No `KesselSyncedResource` for the AWS source

---

### E2E-KESSEL-SRC-s50: Sources POST denied (no access)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users without settings access must not create sources |
| Phase | 1 |

**Fixtures:**
- Denied user with no settings access

**Steps:**
- **Given** a user without settings access
- **When** the user POSTs to `/sources/`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `POST sources-list` returns HTTP 403

---

### E2E-KESSEL-SRC-s51: Sources POST denied (read-only)

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Users with settings read-only must not create sources |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, "e2e-s51-settings-ro", {"settings": {"read": ["*"]}})`

**Steps:**
- **Given** a user with settings read-only access
- **When** the user POSTs to `/sources/`
- **Then** the response status is 403 Forbidden

**Acceptance Criteria:**
- `POST sources-list` returns HTTP 403

---

### E2E-KESSEL-SRC-s52: Sources list filtered by provider access

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Sources list must be filtered by provider access; AWS-only user must not see OCP sources |
| Phase | 1 |

**Fixtures:**
- OCP and AWS sources created as admin
- `seed_access(E2E_WORKSPACE_ID, "e2e-s52-aws-only", {"settings": {"read": ["*"]}, "aws.account": {"read": ["*"]}})`

**Steps:**
- **Given** both OCP and AWS sources exist and a user has only AWS + settings access
- **When** the user requests the sources list
- **Then** OCP sources are excluded by `get_excludes()`

**Acceptance Criteria:**
- `GET sources-list` returns HTTP 200
- No OCP sources appear in the response for the AWS-only user

---

### E2E-KESSEL-SRC-s53: OCP source delete cleans PostgreSQL, deletes integration from Kessel, preserves OCP resources

| Field | Value |
|-------|-------|
| Priority | P0 (Critical) |
| Business Value | Deleting an OCP source must remove PostgreSQL rows and the `integration` Kessel resource, but preserve OCP cluster/node/project KesselSyncedResource rows (cleanup only on data expiry) |
| Phase | 1 |

**Fixtures:**
- `seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}, "openshift.cluster": {"read": ["*"]}})`

**Steps:**
- **Given** an OCP source exists (created via Sources API) with associated Kessel `integration` and `openshift_cluster` resources
- **When** the source is deleted via `DELETE /sources/{id}/`
- **Then** Sources row is removed from PostgreSQL; the `integration` KesselSyncedResource tracking row is deleted; OCP cluster/node/project KesselSyncedResource rows are preserved

**Acceptance Criteria:**
- `DELETE sources-detail` returns HTTP 200 or 204
- `Sources` row no longer exists in PostgreSQL
- `KesselSyncedResource` row for `integration` is removed (source representation cleaned up)
- `KesselSyncedResource` rows for `openshift_cluster`, `openshift_node`, `openshift_project` are preserved (historical data remains queryable)

---

#### UI acceptance coverage summary

| Category | Scenarios | Priority | Count |
|----------|-----------|----------|-------|
| Basic access grant/deny | s1-s7 | P0 | 7 |
| Write grants read | s8, s12 | P0 | 2 |
| Org admin bypass | s9 | P0 | 1 |
| OCP StreamedListObjects basic | s10-s11 | P0 | 2 |
| Provider isolation | s13-s15 | P0 | 3 |
| Cross-provider views | s16-s20d | P1 | 8 |
| Query-parameter filtering | s21-s24 | P2 | 4 |
| Resource-type discovery | s25-s29c | P1 | 8 |
| User-access | s30-s31 | P1 | 2 |
| Forecasts | s32-s35c | P1 | 6 |
| Write operations | s36-s40 | P0 | 5 |
| Realistic profile | s41 | P1 | 1 |
| Resource-level scoping | s42-s45 | P0 | 4 |
| Sources API + Kessel persistence | s46-s53 | P0 | 8 |
| **Total** | **s1-s53** | | **61** |

Priority breakdown: **P0: 32**, **P1: 25**, **P2: 4**

---

## 6. Coverage Summary

### 6.0 Change Log

| Change | Count |
|--------|-------|
| Retired | 46 (management plane externalized, Relations API removed) |
| Updated | 12 (Relations API -> Inventory API v1beta2) |
| New | 29 (workspace resolver, _view/_edit, StreamedListObjects, write_visibility, TLS/CA, config) + 2 (CT-CLEANUP: resource lifecycle verification) |
| Tuple lifecycle (TW) | 26 (15 UT: _create_resource_tuples + delete functions, 5 IT: two-phase creation/deletion integration, 4 CT: creation/lifecycle round-trip, 2 E2E: creation visibility + deletion removal) |
| UI acceptance (s1-s53) | 61 (basic access 7, write-grants-read 2, admin bypass 1, OCP basic 2, provider isolation 3, cross-provider 8, query-params 4, resource-types 8, user-access 2, forecasts 6, writes 5, realistic profile 1, resource-scoping 4, sources API 8) |
| Active (remaining) | 52 (existing active) + 31 (new) + 26 (tuple lifecycle) + 61 (UI acceptance) = **175** |

### 6.1 Active Scenario Count by Tier

| Tier | Active | Retired | P0 | P1 | P2 |
|------|--------|---------|----|----|-----|
| UT   | 67     | 27      | 26 | 30 | 11  |
| IT   | 25     | 7       | 6  | 19 | 0   |
| CT   | 13     | 12      | 8  | 5  | 0   |
| E2E  | 9 + 61 | 0       | 4 + 32 | 5 + 25 | 0 + 4 |
| **Total** | **175** | **46** | **76** | **84** | **15** |

### 6.2 Phase Coverage (Active Only)

| Phase | UT | IT | CT | E2E | Total |
|-------|----|----|----|-----|-------|
| 1     | 67 | 25 | 4  | 61  | 157   |
| 2     | 0  | 0  | 3  | 9   | 12    |
| 3     | 0  | 0  | 6  | 0   | 6     |
| **Total** | **67** | **25** | **13** | **70** | **175** |

### 6.3 Module Coverage (Active Only)

| Module | UT | IT | CT | E2E | Total |
|--------|----|----|-----|-----|-------|
| KESSEL | 62 | 3  | 9   | 70  | 144   |
| SRC    | 0  | 8  | 4   | 0   | 12    |
| SETTINGS | 5 | 0 | 0  | 0   | 5     |
| MW     | 0  | 10 | 0   | 0   | 10    |
| API    | 0  | 2  | 0   | 0   | 2     |
| MASU   | 0  | 2  | 0   | 0   | 2     |
| COSTMODEL | 0 | 1 | 0  | 0   | 1     |

### 6.4 Unit Test Coverage Target

Target: >80% on `koku/koku_rebac/` module + configuration in `koku/koku/settings.py`.

Covered by active UT scenarios:
- `access_provider.py` -- UT-KESSEL-AP-001 through AP-006, AP-008 through AP-017 (16 scenarios: authorization dispatch, _view/_edit compounds, StreamedListObjects for OCP, workspace targeting, user_id subject, write-grants-read, error handling)
- `client.py` -- UT-KESSEL-CL-001 through CL-006 (6 scenarios: insecure channel, CA-based TLS, custom CA, singleton, Inventory-only stub)
- `resource_reporter.py` -- UT-KESSEL-RR-001 through RR-004, RR-006 through RR-009 (8 scenarios: RBAC no-op, reporting with representations, gRPC failure, idempotency, write_visibility, workspace_id, metadata); RR-010 through RR-016 (7 scenarios: _create_resource_tuples POST body, HTTP error, network error, two-phase orchestration, partial success, ReportResource failure skip, idempotency); RR-017 through RR-024 (8 scenarios: _build_delete_request, _delete_from_kessel success/failure, _delete_resource_tuples params/HTTP error/network error, on_resource_deleted two-phase cleanup, cleanup_orphaned_kessel_resources)
- `workspace.py` -- UT-KESSEL-WS-001 through WS-007 (7 scenarios: ShimResolver, RbacV2Resolver, token caching, missing workspace, factory dispatch, error propagation)
- `models.py` -- UT-KESSEL-MDL-001 (1 scenario: uniqueness constraint)
- `settings.py` configuration -- UT-SETTINGS-CFG-001 through CFG-005 (5 scenarios: ONPREM derivation, defaults, auth settings, RBAC_V2_URL, dead config removal)

Retired UT scenarios (27): SEED-001 through SEED-007, SCHEMA-001/002, VIEW-001 through VIEW-004, GRP-001 through GRP-012, AP-007, RR-005 (retired during Inventory API v1beta2 migration)

### 6.5 Integration Test Coverage

Covered by active IT scenarios:
- `middleware.py` -- IT-MW-AUTH-001 through 005, 007, 008, 010 (8 scenarios: auth dispatch, caching, error handling, bootstrap, Kessel cache isolation, TTL)
- `middleware.py` (workspace) -- IT-MW-WS-001 (1 scenario: workspace resolution failure)
- `middleware.py` (URL) -- IT-MW-AUTH-012 (1 scenario: access management URLs removed)
- `resource_reporter.py` -- IT-KESSEL-RR-001 (1 scenario: idempotency); IT-KESSEL-RR-002 (1 scenario: on_resource_deleted two-phase cleanup); IT-CLEANUP-001 (1 scenario: cleanup_orphaned_kessel_resources for deleted provider)
- `provider_builder.py` -- IT-API-PB-001 (1 scenario: OCP cluster reporting); IT-API-PB-002 (1 scenario: two-phase Inventory + Relations creation)
- `ocp_report_db_accessor.py` -- IT-MASU-SYNC-001 (1 scenario: node/project reporting); IT-MASU-SYNC-002 (1 scenario: per-sub-resource tuple creation)
- `cost_models/view.py` -- IT-COSTMODEL-CM-001 (1 scenario: cost model reporting)
- `sources/api/view.py` + `provider_builder.py` -- IT-SRC-CREATE-001, 003-006 (5 scenarios: OCP Kessel hook, CMMO mapping, gRPC failure, idempotency, two-phase Inventory + Relations creation)
- `sources/api/view.py` -- IT-SRC-RETAIN-001 (1 scenario: source deletion deletes integration from Kessel, preserves OCP resources)
- `sources/api/view.py` -- IT-SRC-ONPREM-001, IT-SRC-ONPREM-002 (2 scenarios: CRUD gate and read-only default)

Retired IT scenarios (7): URL-001 through URL-005, AUTH-009, AUTH-011 (retired during Inventory API v1beta2 migration)

### 6.6 Contract Test Coverage

Covered by active CT scenarios:
- Sources Inventory -- CT-SRC-CREATE-001 through CREATE-004 (4 scenarios: OCP reporting, settings resource, idempotency, RBAC no-op)
- Kessel AccessProvider -- CT-KESSEL-AP-001 through AP-003 (3 scenarios, Phase 2: query-layer equivalence, resource ID format, denial equivalence)
- Cleanup Lifecycle -- CT-CLEANUP-001 through CLEANUP-002 (2 scenarios, Phase 3: full cleanup removes from StreamedListObjects, nonexistent delete is graceful)
- Creation Lifecycle -- CT-CREATION-001 through CREATION-003 (3 scenarios, Phase 3: ReportResource + tuple visibility, idempotent tuple creation, negative proof without tuple)
- Full Lifecycle -- CT-LIFECYCLE-001 (1 scenario, Phase 3: create-then-delete round-trip through Koku code paths)

Retired CT scenarios (12): REL-001 through REL-008, LOOKUP-001 through LOOKUP-004 (retired during Inventory API v1beta2 migration)

### 6.7 E2E Test Coverage

Covered by active E2E scenarios:
- E2E-KESSEL-FLOW-001 through FLOW-009 (9 scenarios: full auth chain, denial, revocation, pipeline discovery, cost model, bootstrap, group-based access, creation visibility, deletion removal)
- UI acceptance regression s1-s53 (61 scenarios, IEEE 829 format): basic access grant/deny (7, P0), write-grants-read (2, P0), org admin bypass (1, P0), OCP StreamedListObjects basic (2, P0), provider isolation (3, P0), cross-provider views (8, P1), query-param filtering (4, P2), resource-type discovery (8, P1), user-access (2, P1), forecasts (6, P1), write operations (5, P0), realistic profile (1, P1), resource-level scoping (4, P0), Sources API + Kessel persistence (8, P0)

Implementation: [`koku_rebac/test/test_e2e_regression.py`](../../../koku/koku_rebac/test/test_e2e_regression.py) with `ENABLE_KESSEL_TEST=1`.

### 6.8 Files Not Directly Covered by UT

Covered by IT/CT/E2E or trivial:
- `__init__.py` -- empty
- `apps.py` -- Django boilerplate
- `urls.py` -- declarative routing (covered by IT-MW-AUTH-012)
- `exceptions.py` -- single class definition, tested through UT-KESSEL-AP-003
