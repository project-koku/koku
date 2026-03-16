# Kessel/ReBAC Detailed Design -- Cost Management OCP Integration

| Field         | Value                                                                 |
|---------------|-----------------------------------------------------------------------|
| Jira          | [FLPATH-3294](https://issues.redhat.com/browse/FLPATH-3294)          |
| Parent story  | [FLPATH-2690](https://issues.redhat.com/browse/FLPATH-2690)          |
| Epic          | [FLPATH-2799](https://issues.redhat.com/browse/FLPATH-2799)          |
| HLD           | [kessel-ocp-integration.md](./kessel-ocp-integration.md) |
| Author        | Jordi Gil                                                             |
| Status        | Implemented                                                           |
| Created       | 2026-02-18                                                           |
| Last updated  | 2026-03-11                                                           |

## Table of Contents

1. [Overview and Scope](#1-overview-and-scope)
2. [Configuration and Startup](#2-configuration-and-startup)
3. [AccessProvider Abstraction (Phase 1)](#3-accessprovider-abstraction-phase-1)
4. [Middleware Integration (Phase 1)](#4-middleware-integration-phase-1)
5. [KesselAccessProvider Internals](#5-kesselaccessprovider-internals)
6. [Resource Reporting and Sync (Phase 1)](#6-resource-reporting-and-sync-phase-1)
7. [ZED Schema and Role Seeding](#7-zed-schema-and-role-seeding)
8. [Testing Strategy](#8-testing-strategy)
9. [Deployment and Operations](#9-deployment-and-operations)
10. [Dependencies](#10-dependencies)
11. [Risks and Mitigations](#11-risks-and-mitigations)

---

## 1. Overview and Scope

This document describes the detailed design for integrating Kessel/ReBAC as the authorization backend for Cost Management, replacing RBAC for on-premise deployments and providing a future migration path for SaaS.

### 1.1 Phases

All three phases are delivered in a single branch/PR, using phases as logical checkpoints:

- **Phase 1** -- AccessProvider abstraction, middleware integration, resource reporting, pipeline sync
- **Phase 2** -- `StreamedListObjects()` and `Check()` via Inventory API as the primary Kessel methods for retrieving access lists, complete query-layer transparency

### 1.2 Deployment Matrix

| Environment | Authorization backend | How selected                                                     |
|-------------|-----------------------|------------------------------------------------------------------|
| On-prem     | ReBAC (Kessel)        | `ONPREM=true` forces `AUTHORIZATION_BACKEND=rebac` at startup    |
| SaaS        | RBAC (default)        | `AUTHORIZATION_BACKEND=rbac` (default, no env var needed)        |
| SaaS future | ReBAC (Kessel)        | Unleash flag overrides to `rebac` per org (documented hook only) |

### 1.3 Design Principles

- **Deployment-agnostic code**: The `ONPREM` check is confined to `settings.py` (startup-time derivation). The rest of the codebase reads only `AUTHORIZATION_BACKEND`.
- **Transparent pass-through**: `KesselAccessProvider` returns exactly what Kessel reports. No interpretation, no `"*"` fabrication.
- **Zero changes to query layer**: Koku already supports granular resource ID lists. Permission classes and query filtering work unchanged.
- **Resource lifecycle matches RBAC**: Koku's behavior is identical regardless of backend. Source deletion preserves Kessel resources (historical cost data remains queryable). Kessel Inventory resources and SpiceDB permission tuples are only cleaned up when cost data is purged from PostgreSQL due to retention expiry.

---

## 2. Configuration and Startup

All new settings are added to [`koku/koku/settings.py`](../../../koku/koku/settings.py).

### 2.1 Backend Selection

```python
from koku_rebac.config import resolve_authorization_backend

ONPREM = ENVIRONMENT.bool("ONPREM", default=False)
AUTHORIZATION_BACKEND = resolve_authorization_backend(
    onprem=ONPREM,
    env_value=ENVIRONMENT.get_value("AUTHORIZATION_BACKEND", default="rbac"),
)
```

`ONPREM=true` is the only mandatory env var for on-prem. It forces `AUTHORIZATION_BACKEND=rebac` regardless of any explicit `AUTHORIZATION_BACKEND` value. The `resolve_authorization_backend()` function ([`koku_rebac/config.py`](../../../koku/koku_rebac/config.py)) validates the input and returns one of `"rbac"` or `"rebac"`.

### 2.2 Kessel Connection

One gRPC service (Inventory API v1beta2) is used for all authorization and resource management:

```python
# Inventory API gRPC
KESSEL_INVENTORY_CONFIG = {
    "host": ENVIRONMENT.get_value("KESSEL_INVENTORY_HOST", default="localhost"),
    "port": int(ENVIRONMENT.get_value("KESSEL_INVENTORY_PORT", default="9081")),
}

# TLS and OIDC authentication
KESSEL_CA_PATH = ENVIRONMENT.get_value("KESSEL_CA_PATH", default="")
KESSEL_AUTH_ENABLED = ENVIRONMENT.bool("KESSEL_AUTH_ENABLED", default=ONPREM)
KESSEL_AUTH_CLIENT_ID = ENVIRONMENT.get_value("KESSEL_AUTH_CLIENT_ID", default="")
KESSEL_AUTH_CLIENT_SECRET = ENVIRONMENT.get_value("KESSEL_AUTH_CLIENT_SECRET", default="")
KESSEL_AUTH_OIDC_ISSUER = ENVIRONMENT.get_value("KESSEL_AUTH_OIDC_ISSUER", default="")

# Relations API REST (for SpiceDB tuple management)
KESSEL_RELATIONS_URL = ENVIRONMENT.get_value("KESSEL_RELATIONS_URL", default="http://localhost:8100")
KESSEL_TUPLES_PATH = ENVIRONMENT.get_value("KESSEL_TUPLES_PATH", default="/api/authz/v1beta1/tuples")
```

When `KESSEL_CA_PATH` is non-empty, the client reads the CA certificate and uses `grpc.ssl_channel_credentials()` for a secure channel. When empty, the client uses an insecure channel (suitable for local development). OIDC-based authentication is enabled via `KESSEL_AUTH_ENABLED=true`, requiring the client ID, secret, and issuer URL to be set.

### 2.3 Schema Version Tracking

Schema versioning is managed externally via the ZED schema file ([`dev/kessel/schema.zed`](../../../dev/kessel/schema.zed)) and the `zed` CLI. No Django settings entry is needed.

### 2.4 Cache Configuration

A new `kessel` cache entry mirrors the existing `rbac` cache (see [`settings.py` line 294](../../../koku/koku/settings.py#L294)):

```python
class CacheEnum(StrEnum):
    default = "default"
    api = "api"
    rbac = "rbac"
    kessel = "kessel"  # new
    worker = "worker"

```

The `CACHES` dict gets a new `CacheEnum.kessel` entry identical in structure to `CacheEnum.rbac`, with `TIMEOUT` set to `ENVIRONMENT.get_value("KESSEL_CACHE_TIMEOUT", default=300)`. The test `CACHES` block also gets the new entry with `DummyCache`.

### 2.5 App Registration

```python
INSTALLED_APPS = [
    ...
    "koku_rebac",  # new
]

SHARED_APPS = (
    ...
    "koku_rebac",  # new -- KesselSyncedResource lives in public schema
)
```

### 2.6 Bootstrap Configuration

| Setting              | On-prem mandatory? | Purpose                                             |
|----------------------|--------------------|-----------------------------------------------------|
| `ONPREM=true`        | Yes                | Forces `AUTHORIZATION_BACKEND=rebac`                |
| `ENHANCED_ORG_ADMIN` | No (default False) | Temporary bootstrap aid for first admin             |
| `KESSEL_INVENTORY_*` | Yes                | Inventory API gRPC endpoint                         |
| `KESSEL_CA_PATH`     | No                 | TLS CA certificate path (empty = insecure)          |
| `KESSEL_AUTH_*`      | Conditional        | OIDC auth settings (when `KESSEL_AUTH_ENABLED=true`) |

---

## 3. AccessProvider Abstraction (Phase 1)

New file: [`koku/koku_rebac/access_provider.py`](../../../koku/koku_rebac/access_provider.py)

### 3.1 Interface Contract

Both providers implement the same duck-typed interface:

- `get_access_for_user(self, user) -> dict` -- returns the access dict
- `get_cache_ttl(self) -> int` -- returns cache TTL in seconds

### 3.2 Implementations

**`RBACAccessProvider`** -- wraps existing [`RbacService`](../../../koku/koku/rbac.py) with zero changes to `rbac.py`:

```python
class RBACAccessProvider:
    """Wraps the existing RbacService for legacy compatibility."""

    def __init__(self):
        self._service = RbacService()

    def get_access_for_user(self, user):
        """Delegate to the existing RbacService."""
        return self._service.get_access_for_user(user)

    def get_cache_ttl(self) -> int:
        return self._service.get_cache_ttl()
```

**`KesselAccessProvider`** -- workspace-Check-first pattern with StreamedListObjects fallback, builds the identical dict structure that `_apply_access()` returns:

```python
class KesselAccessProvider:
    """Queries Kessel Inventory API v1beta2 for user access."""

    def __init__(self) -> None:
        self._workspace_resolver = get_workspace_resolver()

    def get_access_for_user(self, user) -> dict:
        """Get resource access for a user from Kessel."""
        client = get_kessel_client()
        access = _init_empty_access()
        org_id = user.customer.org_id
        user_id = getattr(user, "user_id", None) or user.username

        workspace_id = self._workspace_resolver.resolve(org_id)

        for koku_type, kessel_type in KOKU_TO_KESSEL_TYPE_MAP.items():
            if koku_type in CHECK_ONLY_TYPES:
                self._resolve_workspace_access(client, access, koku_type, kessel_type, workspace_id, user_id)
            else:
                self._resolve_per_resource_access(client, access, koku_type, kessel_type, workspace_id, user_id)

        return access

    def get_cache_ttl(self) -> int:
        return int(settings.CACHES.get("kessel", {}).get("TIMEOUT", 300))
```

### 3.3 Factory

```python
def get_access_provider():
    """Factory: return the access provider for the configured backend."""
    if settings.AUTHORIZATION_BACKEND == "rebac":
        return KesselAccessProvider()
    return RBACAccessProvider()
```

Returns a new instance per call. The `KesselAccessProvider` holds a workspace resolver (stateless) and creates a `KesselClient` singleton via `get_kessel_client()`.

### 3.4 Critical Contract

`KesselAccessProvider.get_access_for_user()` MUST return the same dict shape as `RbacService.get_access_for_user()`:

**RBAC example** (wildcard access):

```python
{
    "aws.account": {"read": ["*"]},
    "openshift.cluster": {"read": ["*"]},
    "cost_model": {"read": ["*"], "write": ["*"]},
    "settings": {"read": ["*"], "write": ["*"]},
    ...
}
```

**ReBAC example** (explicit IDs, no wildcards):

```python
{
    "aws.account": {"read": []},
    "openshift.cluster": {"read": ["cluster-uuid-1", "cluster-uuid-2"]},
    "cost_model": {"read": ["uuid1", "uuid2"], "write": ["uuid1"]},
    "settings": {"read": ["settings-org123"], "write": ["settings-org123"]},
    ...
}
```

### 3.5 Why Zero Changes to Permission Classes and Query Layer

Koku's existing permission classes and query filtering already support both patterns:

- **Permission classes** (Layer 1): gate access with `len(read_access) > 0`. An empty list from ReBAC means "no access" -- handled identically to RBAC returning no permissions.
- **Query engine** (Layer 2): [`QueryParameters._set_access()`](../../../koku/api/query_params.py#L266) checks `has_wildcard(access_list)`. If wildcard, no filtering. If specific IDs, applies `QueryFilter(parameter=access, ...)`. ReBAC always returns specific IDs.
- **Cost model view**: [`CostModelViewSet.get_queryset()`](../../../koku/cost_models/view.py) does `queryset.filter(uuid__in=read_access_list)` when not wildcard.

---

## 4. Middleware Integration (Phase 1)

Modifications to [`koku/koku/middleware.py`](../../../koku/koku/middleware.py).

### 4.1 Changes to IdentityHeaderMiddleware

From `IdentityHeaderMiddleware.__init__()` (see `middleware.py`):

```python
class IdentityHeaderMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self._provider = get_access_provider()
```

From `IdentityHeaderMiddleware._get_access()`:

```python
def _get_access(self, user):
    """Obtain access for given user from the configured authorization provider."""
    if settings.ENHANCED_ORG_ADMIN and user.admin:
        return {}
    return self._provider.get_access_for_user(user)
```

### 4.2 Cache Key Selection

From `IdentityHeaderMiddleware._get_auth_cache_name()` and the process_request flow:

```python
def _get_auth_cache_name(self) -> str:
    """Return the cache name for the configured authorization backend."""
    if settings.AUTHORIZATION_BACKEND == "rebac":
        return CacheEnum.kessel
    return CacheEnum.rbac

# In process_request:
cache_name = self._get_auth_cache_name()
cache = caches[cache_name]
user_access = cache.get(f"{user.uuid}_{org_id}")

if not user_access:
    try:
        user_access = self._get_access(user)
    except RbacConnectionError as err:
        return HttpResponseFailedDependency({"source": "Rbac", "exception": err})
    except KesselConnectionError as err:
        return HttpResponseFailedDependency({"source": "Kessel", "exception": err})
    cache.set(f"{user.uuid}_{org_id}", user_access, self._provider.get_cache_ttl())
```

**Note**: `KesselConnectionError` is defined in `koku_rebac/exceptions.py` and caught here as a safety net. The current `KesselAccessProvider` catches all exceptions internally and never raises it — see §5.1.

### 4.3 Settings Sentinel Creation

Add resource reporting hook in `create_customer()` at [line 239](../../../koku/koku/middleware.py#L239), after the customer is saved:

```python
@staticmethod
def create_customer(account, org_id, request_method):
    try:
        with transaction.atomic():
            ...
            if request_method and request_method not in ["GET", "HEAD"]:
                customer.save()
                UNIQUE_ACCOUNT_COUNTER.inc()
                LOG.info("Created new customer from account_id %s and org_id %s.", account, org_id)
                on_resource_created("settings", f"settings-{org_id}", org_id)
    ...
```

### 4.4 Unchanged Behaviors

- `ENHANCED_ORG_ADMIN` bypass (line 272) works identically for both backends
- `DEVELOPMENT_IDENTITY` bypass (line 374) remains unchanged
- `DEVELOPMENT` passthrough remains unchanged

### 4.5 Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Middleware as IdentityHeaderMiddleware
    participant Cache as Redis Cache
    participant Provider as AccessProvider
    participant Backend as RBAC or Kessel

    Client->>Middleware: HTTP request with x-rh-identity
    Middleware->>Middleware: Extract identity, resolve customer/user

    alt ENHANCED_ORG_ADMIN and user.admin
        Middleware->>Client: user.access = {} (full access)
    else Cache hit
        Middleware->>Cache: get(user.uuid_org_id)
        Cache-->>Middleware: cached access dict
        Middleware->>Client: user.access = cached
    else Cache miss
        Middleware->>Cache: get(user.uuid_org_id)
        Cache-->>Middleware: None
        Middleware->>Provider: get_access_for_user(user)
        Provider->>Backend: RBAC HTTP or Kessel gRPC
        Backend-->>Provider: permissions data
        Provider-->>Middleware: access dict
        Middleware->>Cache: set(user.uuid_org_id, access, ttl)
        Middleware->>Client: user.access = access
    end
```

---

## 5. KesselAccessProvider Internals

### 5.1 Execution Flow

From `KesselAccessProvider` in [`access_provider.py`](../../../koku/koku_rebac/access_provider.py):

```python
def _resolve_per_resource_access(
    self, client, access: dict, koku_type: str, kessel_type: str, workspace_id: str, user_id: str,
) -> None:
    for operation in RESOURCE_TYPES.get(koku_type, ["read"]):
        suffix = PERMISSION_SUFFIX_MAP.get(operation, operation)
        permission = f"cost_management_{kessel_type}_{suffix}"

        if self._check_workspace_permission(client, workspace_id, permission, user_id):
            access[koku_type][operation] = ["*"]
        else:
            resource_ids = self._streamed_list_objects(client, kessel_type, operation, user_id)
            if resource_ids:
                access[koku_type][operation] = resource_ids

        if operation == "write" and access[koku_type].get("write"):
            write_ids = access[koku_type]["write"]
            read_ids = access[koku_type].get("read", [])
            if write_ids == ["*"]:
                access[koku_type]["read"] = ["*"]
            elif read_ids != ["*"]:
                merged = list(dict.fromkeys(read_ids + write_ids))
                access[koku_type]["read"] = merged

def _streamed_list_objects(self, client, kessel_type, operation, user_id) -> list[str]:
    """Call StreamedListObjects and return the list of resource IDs."""
    request = _build_streamed_list_request(kessel_type, operation, user_id)
    try:
        resource_ids = []
        for response in client.inventory_stub.StreamedListObjects(request):
            if response.object and response.object.resource_id:
                resource_ids.append(response.object.resource_id)
        return resource_ids
    except Exception:
        LOG.exception(
            log_json(msg="Kessel StreamedListObjects failed", resource_type=kessel_type, operation=operation)
        )
        return []

def _check_workspace_permission(self, client, workspace_id, permission, user_id) -> bool:
    """Check a single workspace-level permission. Returns True if ALLOWED."""
    request = _build_check_request(workspace_id, permission, user_id)
    try:
        resp = client.inventory_stub.Check(request)
        return resp.allowed == allowed_pb2.ALLOWED_TRUE
    except Exception:
        LOG.exception(
            log_json(msg="Kessel Check failed", permission=permission)
        )
        return False
```

Key design details:

- **Workspace-check-first pattern**: For every per-resource type, a workspace-level `Check(rbac/workspace:{workspace_id}, cost_management_{type}_{suffix}, user)` runs first. If ALLOWED, the user gets wildcard `["*"]` (org-wide role covers all resources of this type). Only when DENIED does `StreamedListObjects` run for per-resource IDs. This ensures users with org-wide roles (e.g., cost-administrator) always get wildcard access immediately, even when new resources have been registered since the last cache fill.
- **CHECK_ONLY_TYPES**: Settings is a capability, not a per-resource concept — it uses `_resolve_workspace_access` (Check only, no StreamedListObjects). Currently `CHECK_ONLY_TYPES = {"settings"}`.
- **Compound permission names**: Koku operations are mapped via `PERMISSION_SUFFIX_MAP`: `read` -> `_view`, `write` -> `_edit`. The compound name `cost_management_{type}_{suffix}` resolves through the ZED schema's computed permissions (e.g., `cost_management_settings_view = settings_read + settings_all + all_read + all_all + all_all_all`).
- **Workspace resolver**: On-prem uses `ShimResolver` (returns `org_id` directly). SaaS uses `RbacV2Resolver` (fetches default workspace ID from RBAC v2 API).
- **On success, always returns a dict.** Empty lists for resource types with no access. This matches the middleware's expectation for both backends.
- **gRPC errors are logged but do not propagate.** `_check_workspace_permission` and `_streamed_list_objects` catch all exceptions and return `False` / `[]`. This is a fail-open-per-type design: if Kessel is unreachable for one type, that type returns no access (empty list), but other types are still queried.
- **StreamedListObjects relation**: Uses the raw operation name (`"read"` or `"write"`) as the relation, not the compound permission name. The resource type's `read`/`write` permission in the ZED schema handles the full resolution chain.

### 5.2 Transparent Pass-Through Principle

`KesselAccessProvider` returns exactly what Kessel reports:

- For every operation, a workspace-level `Check(rbac/workspace:{workspace_id}, cost_management_{type}_{suffix})` runs first. If ALLOWED, we return `["*"]` (org-wide role).
- For `read` operations where the workspace Check is DENIED, `StreamedListObjects()` returns per-resource IDs as fallback.
- For `write` operations where the workspace Check is DENIED, the user has no write access (returns `[]`).
- Write-grants-read: if `write` yields `["*"]`, `read` is also set to `["*"]`; if `write` yields specific IDs, those IDs are merged into `read`.
- If no resources of a type exist (e.g., no AWS accounts on-prem), Kessel returns nothing and we return `[]`.
- The query layer handles both cases: specific IDs trigger filtered queries, empty lists result in no data or 403 depending on the permission class.

### 5.3 Performance Consideration

Returning explicit ID lists instead of `"*"` means the query layer always applies `WHERE uuid IN (...)` filters. For users with access to many resources, this is functionally equivalent to no filter but marginally less efficient. This is an acceptable trade-off for correctness and deployment-agnostic behavior. Optimization (e.g., query-layer awareness of "all resources" case) can be added later if needed.

> **Design rationale**: The adapter pattern (bulk-fetch access, filter locally) was chosen over per-resource `Check()` calls because Koku's query layer needs a **set of allowed IDs** to build SQL `WHERE` clauses -- not a boolean per resource. `StreamedListObjects` answers this in O(1) calls per type versus O(N) `Check()` calls. See [Authorization Delegation DD §5 -- "Why fetch all access, intersect locally"](./kessel-authorization-delegation-dd.md#why-fetch-all-access-intersect-locally----not-check-per-resource) for the full analysis.

### 5.4 Koku-to-Kessel Type Mapping

Defined as a constant in [`koku/koku_rebac/access_provider.py`](../../../koku/koku_rebac/access_provider.py):

| Koku `RESOURCE_TYPES` key  | Kessel resource type                        | Koku DB identifier         |
|-----------------------------|---------------------------------------------|----------------------------|
| `openshift.cluster`         | `cost_management/openshift_cluster`         | `Provider.uuid`            |
| `openshift.node`            | `cost_management/openshift_node`            | node name string           |
| `openshift.project`         | `cost_management/openshift_project`         | namespace name string      |
| `cost_model`                | `cost_management/cost_model`                | `CostModel.uuid`           |
| `settings`                  | `cost_management/settings`                  | `settings-{org_id}`        |
| `aws.account`               | `cost_management/aws_account`               | usage account ID string    |
| `aws.organizational_unit`   | `cost_management/aws_organizational_unit`   | org unit ID string         |
| `azure.subscription_guid`   | `cost_management/azure_subscription_guid`   | subscription GUID string   |
| `gcp.account`               | `cost_management/gcp_account`               | account ID string          |
| `gcp.project`               | `cost_management/gcp_project`               | project ID string          |
| `integration`               | `cost_management/integration`               | `Provider.uuid`            |

> **Note**: `cost_management/openshift_vm` is defined in the ZED schema but is not yet in `KOKU_TO_KESSEL_TYPE_MAP` or `IMMEDIATE_WRITE_TYPES`. It will be added when Koku's data pipeline supports VM-level cost data.

All resource types are queried uniformly. No special-casing by type. On on-prem OCP, Kessel has no AWS/Azure/GCP resources registered, so those queries return empty lists naturally. `integration` is a computed-visibility resource — its `read` permission is derived from structural relationships (`has_cluster`, `has_project`), not from direct role bindings. See the [On-Prem Workspace Management ADR](./onprem-workspace-management-adr.md#integration-as-first-class-kessel-resource) for details.

### 5.5 Permission Mapping

Koku operation names are mapped to Kessel compound permission names via `PERMISSION_SUFFIX_MAP` in [`access_provider.py`](../../../koku/koku_rebac/access_provider.py). The mapping is `f"cost_management_{kessel_type}_{suffix}"` where `suffix = PERMISSION_SUFFIX_MAP.get(operation, operation)`:

| Koku operation | Kessel compound permission pattern | Example |
|----------------|--------------------------------------|---------|
| `read`         | `cost_management_{type}_view`        | `cost_management_openshift_cluster_view` |
| `write`        | `cost_management_{type}_edit`        | `cost_management_cost_model_edit` |

These compound permissions are resolved by SpiceDB through the ZED schema's permission propagation chain (`principal -> role_binding -> role -> permission`). The `_view` suffix maps to read access and `_edit` maps to write access in the schema.

---

## 6. Resource Reporting and Sync (Phase 1)

### 6.1 Tracking Model

New file: [`koku/koku_rebac/models.py`](../../../koku/koku_rebac/models.py) (registered in `SHARED_APPS` -- public schema):

```python
class KesselSyncedResource(models.Model):
    resource_type = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=256)
    org_id = models.CharField(max_length=64)
    kessel_synced = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kessel_synced_resource"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "resource_id", "org_id"],
                name="uq_kessel_sync_type_id_org",
            ),
        ]
        indexes = [
            models.Index(fields=["org_id"], name="idx_kessel_sync_org"),
            models.Index(fields=["resource_type", "org_id"], name="idx_kessel_sync_type_org"),
        ]
```

### 6.2 Transparent Resource Reporter

New file: [`koku/koku_rebac/resource_reporter.py`](../../../koku/koku_rebac/resource_reporter.py)

The reporter is called unconditionally by Koku's core code. The backend decides internally what to do:

- **RBAC backend**: all methods are no-ops (RBAC doesn't track individual resources)
- **ReBAC backend**: calls Inventory API `ReportResource()` first, then records success in `KesselSyncedResource`

From `on_resource_created()` in [`resource_reporter.py`](../../../koku/koku_rebac/resource_reporter.py):

```python
def on_resource_created(resource_type: str, resource_id: str, org_id: str) -> None:
    """Report a new resource to Kessel Inventory AND create SpiceDB tuples."""
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return

    client = get_kessel_client()
    request = _build_report_request(resource_type, resource_id, org_id)

    inventory_ok = True
    try:
        client.inventory_stub.ReportResource(request)
    except grpc.RpcError:
        inventory_ok = False
        LOG.warning(
            log_json(msg="Failed to report resource to Kessel",
                     resource_type=resource_type, resource_id=resource_id),
            exc_info=True,
        )

    tuple_ok = _create_resource_tuples(resource_type, resource_id, org_id)
    _track_synced_resource(resource_type, resource_id, org_id, synced=(inventory_ok and tuple_ok))
```

Two-phase creation ensures both Kessel Inventory metadata and the SpiceDB `t_workspace` tuple are created. The `t_workspace` tuple (written via Relations API REST POST) makes the resource discoverable by `StreamedListObjects`. Tracking always occurs — `synced=False` when either phase fails, allowing retry on the next pipeline cycle.

The `_create_resource_tuples()` payload (exact JSON sent to Relations API):

```python
payload = {
    "upsert": True,
    "tuples": [{
        "resource": {
            "type": {"namespace": "cost_management", "name": resource_type},
            "id": resource_id,
        },
        "relation": "t_workspace",
        "subject": {
            "subject": {
                "type": {"namespace": "rbac", "name": "workspace"},
                "id": org_id,
            }
        },
    }],
}
```

### 6.3 Hook Points

All hooks call the reporter unconditionally. The reporter no-ops for RBAC.

| Hook location | Resource type | Resource ID | When triggered |
|---|---|---|---|
| [`ProviderBuilder.create_provider_from_source()`](../../../koku/api/provider/provider_builder.py#L122) | `openshift_cluster` | `provider.uuid` | New OCP source registered |
| [`ocp_report_db_accessor.populate_openshift_cluster_information_tables()`](../../../koku/masu/database/ocp_report_db_accessor.py#L749) | `openshift_node`, `openshift_project` | node name, namespace name | Pipeline processes OCP data |
| [`CostModelViewSet.perform_create()`](../../../koku/cost_models/view.py) | `cost_model` | `cost_model.uuid` | New cost model created |
| [`IdentityHeaderMiddleware.create_customer()`](../../../koku/koku/middleware.py#L239) | `settings` | `settings-{org_id}` | New org first seen |

### 6.3.1 Sources API Flow (On-Prem)

When `ONPREM=true`, the Sources API is extended with full CRUD capabilities ([`view.py`](../../../koku/sources/api/view.py)).
The creation flow for OCP sources automatically triggers Kessel resource reporting:

```
POST /api/cost-management/v1/sources/
  -> SourcesViewSet.create()
    -> AdminSourcesSerializer.create()
      -> ProviderBuilder.create_provider_from_source()
        -> _report_ocp_resource(provider.uuid, org_id)
          -> on_resource_created("openshift_cluster", uuid, org_id)
            -> Kessel Inventory ReportResource gRPC
```

Key details:
- The `ONPREM` gate at module level in [`view.py`](../../../koku/sources/api/view.py) enables `CreateModelMixin`, `UpdateModelMixin`, and `DestroySourceMixin`
- CMMO compatibility: `source_type_id` and `source_ref` fields on serializers ([`serializers.py`](../../../koku/sources/api/serializers.py)) allow operators to create sources using CMMO IDs (e.g., `"1"` for OCP) via [`source_type_mapping.py`](../../../koku/sources/api/source_type_mapping.py)
- On-prem is OCP-only; the `_report_ocp_resource()` hook in `ProviderBuilder` fires exclusively for OCP providers

### 6.3.2 Deletion Policy

**Most resources are NOT removed from Kessel when a source is deleted** — OCP clusters, nodes, projects, and cost models remain in Kessel so that historical cost data (still in PostgreSQL) remains queryable under the original authorization grants.

**Exception: the `integration` resource IS deleted.** When `DestroySourceMixin.destroy()` runs on-prem, it calls `on_resource_deleted("integration", str(source.source_uuid), org_id)` after destroying the Koku provider. This removes the integration from Kessel Inventory, deletes all its SpiceDB tuples (including `t_workspace` and structural `has_cluster` tuples), and removes the `KesselSyncedResource` tracking row. The rationale: the `integration` resource represents the source itself, not historical data — once the source is deleted, the integration should no longer be discoverable.

### 6.3.3 Data Expiry Cleanup

**Resources ARE removed from Kessel when cost data is purged from PostgreSQL due to retention expiry.** When `remove_expired_data` (in [`tasks.py`](../../../koku/masu/processor/tasks.py)) fully purges a provider's data past the retention period, the corresponding Kessel Inventory resources and SpiceDB permission tuples must also be cleaned up via `DeleteResource`. The `KesselSyncedResource` tracking rows are deleted at the same time. *(Target design -- requires assessment of `OCPReportDBCleaner` interaction and implementation.)*

### 6.4 Error Handling

Kessel sync failures are **non-fatal** (unlike access queries in Section 5.1):
- The resource is created in Postgres normally — a Kessel outage must never block data ingestion
- The gRPC error is logged; a `KesselSyncedResource` row is created (or updated) with `kessel_synced=False`, tracking the failure
- Retry occurs on the next pipeline cycle (idempotent `ReportResource` call); `kessel_synced` flips to `True` on success

The rationale for non-fatal error handling: resource reporting runs on the **write path** (background/pipeline work — fire-and-forget with retry). Access queries (§5.1) are on the **request path** and fail-open per-type: an unreachable Kessel returns no access for the affected type but does not block the entire request.

### 6.5 Resource Lifecycle

The design principle is that Koku's behavior is identical regardless of authorization backend.

**RBAC today:**

- **Create**: Koku creates resource in Postgres. RBAC doesn't know. Users with `"*"` see it; users with specific IDs need an admin to add the ID in RBAC UI.
- **Update**: Koku updates in Postgres. RBAC doesn't know or care.
- **Delete**: Koku deletes from Postgres. RBAC doesn't know. Stale IDs in RBAC are harmless.
- **Org removal**: `remove_stale_tenants` drops the Postgres schema. RBAC doesn't know.

**ReBAC mirrors this:**

- **Create**: Koku creates in Postgres. Reporter reports to Kessel (RBAC: no-op). Users with tenant-level bindings see it via `StreamedListObjects()`.
- **Update**: No Kessel action. Resource IDs are immutable (`Provider.uuid`, node name, namespace name, `CostModel.uuid`). Kessel tracks identity, not attributes.
- **Delete (source removal)**: The `integration` resource is deleted from Kessel (Inventory + SpiceDB tuples). OCP clusters, nodes, and projects remain in Kessel — historical cost data stays queryable. Both backends preserve historical data access; the integration deletion is a cleanup of the source representation itself.
- **Delete (data expiry)**: When `remove_expired_data` purges cost data past retention, `DeleteResource` is called on Kessel Inventory API to remove the resource and its SpiceDB tuples. `KesselSyncedResource` tracking rows are also deleted.
- **Org removal**: [`remove_stale_tenants`](../../../koku/masu/processor/tasks.py#L1131) drops the Postgres schema. Kessel resources for the org should also be cleaned up (hook point for future implementation).

### 6.6 Complete Resource Lifecycle Summary

| Resource | Created | Updated | Deleted from Kessel? |
|---|---|---|---|
| Role definitions (global) | `seed-roles.yaml` at deploy | `zed` CLI (additive schema) | Never (global definitions) |
| Settings sentinel (per-org) | `create_customer()` middleware | N/A (sentinel) | On org removal (future) |
| Integration | `create_provider_from_source()` + structural `has_cluster` tuple | No-op (source_uuid unchanged) | **Yes on source deletion** (`on_resource_deleted` in `DestroySourceMixin`); Yes on data expiry |
| OCP Cluster | `create_provider_from_source()` | No-op (UUID unchanged) | No on source deletion (historical data preserved); Yes on data expiry via `remove_expired_data` |
| OCP Nodes | `populate_node_table()` pipeline | No-op (name unchanged) | No on source deletion; Yes on data expiry |
| OCP Projects | `populate_project_table()` pipeline + structural `has_project` tuple | No-op (name unchanged) | No on source deletion; Yes on data expiry |
| Cost Model | `CostModelViewSet.perform_create()` | No-op (UUID unchanged) | No on deletion; Yes on data expiry |
| Role bindings (per-user) | `kessel-admin.sh` / `zed` CLI | Delete + recreate | Yes, via `kessel-admin.sh` / `zed` CLI |

---

## 7. ZED Schema and Role Seeding

### 7.1 Production ZED Schema (Current State)

Source: [`RedHatInsights/rbac-config/configs/prod/schemas/schema.zed`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/schemas/schema.zed)

The production schema already defines **23 cost_management permissions** on `rbac/role` (lines 163-208):

```zed
definition rbac/role {
    ...
    permission cost_management_all_all = t_cost_management_all_all
    relation t_cost_management_all_all: rbac/principal:*
    permission cost_management_aws_account_all = t_cost_management_aws_account_all
    relation t_cost_management_aws_account_all: rbac/principal:*
    permission cost_management_aws_account_read = t_cost_management_aws_account_read
    relation t_cost_management_aws_account_read: rbac/principal:*
    permission cost_management_aws_organizational_unit_all = t_cost_management_aws_organizational_unit_all
    relation t_cost_management_aws_organizational_unit_all: rbac/principal:*
    permission cost_management_aws_organizational_unit_read = t_cost_management_aws_organizational_unit_read
    relation t_cost_management_aws_organizational_unit_read: rbac/principal:*
    permission cost_management_azure_subscription_guid_all = t_cost_management_azure_subscription_guid_all
    relation t_cost_management_azure_subscription_guid_all: rbac/principal:*
    permission cost_management_azure_subscription_guid_read = t_cost_management_azure_subscription_guid_read
    relation t_cost_management_azure_subscription_guid_read: rbac/principal:*
    permission cost_management_cost_model_all = t_cost_management_cost_model_all
    relation t_cost_management_cost_model_all: rbac/principal:*
    permission cost_management_cost_model_read = t_cost_management_cost_model_read
    relation t_cost_management_cost_model_read: rbac/principal:*
    permission cost_management_cost_model_write = t_cost_management_cost_model_write
    relation t_cost_management_cost_model_write: rbac/principal:*
    permission cost_management_gcp_account_all = t_cost_management_gcp_account_all
    relation t_cost_management_gcp_account_all: rbac/principal:*
    permission cost_management_gcp_account_read = t_cost_management_gcp_account_read
    relation t_cost_management_gcp_account_read: rbac/principal:*
    permission cost_management_gcp_project_all = t_cost_management_gcp_project_all
    relation t_cost_management_gcp_project_all: rbac/principal:*
    permission cost_management_gcp_project_read = t_cost_management_gcp_project_read
    relation t_cost_management_gcp_project_read: rbac/principal:*
    permission cost_management_openshift_cluster_all = t_cost_management_openshift_cluster_all
    relation t_cost_management_openshift_cluster_all: rbac/principal:*
    permission cost_management_openshift_cluster_read = t_cost_management_openshift_cluster_read
    relation t_cost_management_openshift_cluster_read: rbac/principal:*
    permission cost_management_openshift_node_all = t_cost_management_openshift_node_all
    relation t_cost_management_openshift_node_all: rbac/principal:*
    permission cost_management_openshift_node_read = t_cost_management_openshift_node_read
    relation t_cost_management_openshift_node_read: rbac/principal:*
    permission cost_management_openshift_project_all = t_cost_management_openshift_project_all
    relation t_cost_management_openshift_project_all: rbac/principal:*
    permission cost_management_openshift_project_read = t_cost_management_openshift_project_read
    relation t_cost_management_openshift_project_read: rbac/principal:*
    permission cost_management_settings_all = t_cost_management_settings_all
    relation t_cost_management_settings_all: rbac/principal:*
    permission cost_management_settings_read = t_cost_management_settings_read
    relation t_cost_management_settings_read: rbac/principal:*
    permission cost_management_settings_write = t_cost_management_settings_write
    relation t_cost_management_settings_write: rbac/principal:*
    ...
}
```

**Gap**: These permissions exist on `rbac/role` but are **NOT yet wired** through `rbac/role_binding` or `rbac/tenant`. The `role_binding` and `tenant` definitions in prod only propagate permissions for other services (HBI, notifications, etc.), not cost management. This means the authorization chain `principal -> role_binding -> tenant` cannot yet evaluate cost management permissions. Completing this wiring is part of the schema PR to `rbac-config`.

**Full delta tracking**: A comprehensive comparison of our local `dev/kessel/schema.zed` against the SaaS production schema -- including naming divergences, missing `_all` verb permissions, structural type differences, and a step-by-step reconciliation plan -- is maintained in [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md).

### 7.2 SaaS Role Definitions

Source: [`RedHatInsights/rbac-config/configs/prod/roles/cost-management.json`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/roles/cost-management.json)

These are the 5 standard roles used in SaaS production. The role seeding process (see Section 7.3) must create these exact role instances with the exact same permission mappings:

| Role name | RBAC slug | RBAC permissions | Description |
|---|---|---|---|
| Cost Administrator | `cost-administrator` | `cost-management:*:*` + 14 individual read/write permissions (see [seed-roles.yaml](../../../dev/kessel/seed-roles.yaml)) | All cost management permissions |
| Cost Cloud Viewer | `cost-cloud-viewer` | `cost-management:aws.account:read`, `cost-management:aws.organizational_unit:read`, `cost-management:azure.subscription_guid:read`, `cost-management:gcp.account:read`, `cost-management:gcp.project:read` | Cloud resource types (read-only) |
| Cost OpenShift Viewer | `cost-openshift-viewer` | `cost-management:openshift.cluster:read`, `cost-management:openshift.node:read`, `cost-management:openshift.project:read` | OpenShift resource types (read-only) |
| Cost Price List Administrator | `cost-price-list-administrator` | `cost-management:cost_model:read`, `cost-management:cost_model:write` | Cost model read/write |
| Cost Price List Viewer | `cost-price-list-viewer` | `cost-management:cost_model:read` | Cost model read-only |

### 7.3 RBAC Permission to Kessel Relation Mapping

The mapping from RBAC permission strings (e.g., `cost-management:openshift.cluster:*`) to Kessel relation names (e.g., `t_cost_management_openshift_cluster_all`) is defined declaratively in [`dev/kessel/seed-roles.yaml`](../../../dev/kessel/seed-roles.yaml). This file is the single source of truth for role definitions and their permission mappings.

The mapping follows a deterministic convention: the RBAC permission `cost-management:{resource_type}:{verb}` maps to the Kessel relation `t_cost_management_{resource_type}_{verb}` on `rbac/role`. Wildcard permissions (`*:*` or `{type}:*`) expand to all matching relations for that scope.

### 7.4 Role Seeding Process

Role seeding is handled by [`deploy-kessel.sh`](../../../dev/kessel/deploy-kessel.sh) which processes `seed-roles.yaml` and writes the resulting tuples to SpiceDB via the Relations API. This script is invoked as a Helm post-install hook.

For each role defined in `seed-roles.yaml`:

1. Creates the role instance tuple: `rbac/role:{slug}` (implicit on first relation write)
2. For each permission entry, creates a tuple: `rbac/role:{slug}#{relation} rbac/principal:*`

**Example**: Seeding "Cost OpenShift Viewer" produces two tuples:

```
rbac/role:cost-openshift-viewer#t_cost_management_openshift_cluster_all@rbac/principal:*
rbac/role:cost-openshift-viewer#t_cost_management_openshift_cluster_read@rbac/principal:*
```

### 7.5 Roles Source

Role definitions are stored in `seed-roles.yaml` (committed to the repository). This file is derived from the SaaS production [`cost-management.json`](https://github.com/RedHatInsights/rbac-config/blob/master/configs/prod/roles/cost-management.json) and must be kept in sync when upstream roles change. The YAML format is suitable for air-gapped on-prem deployments (no network fetching required).

### 7.6 Authorization Hierarchy

> **Update (2026-03-06)**: The on-prem deployment now uses `rbac/workspace` as a core authorization primitive, not just `rbac/tenant`. The workspace hierarchy enables team-based resource scoping, which is implemented by `kessel-admin.sh`, consumed by `KesselAccessProvider`, and will be managed at runtime by the [ReBAC Bridge](./rebac-bridge-design.md). The original "workspaces not used" statement below applied to the initial SaaS-oriented design and is no longer accurate for on-prem.

The authorization chain uses a workspace hierarchy between tenant and resources:

```
tenant:{org_id}
  └── workspace:{org_id}        (org-level, linked via t_parent → tenant)
        ├── workspace:{team-A}   (team-level, linked via t_parent → workspace:{org_id})
        └── workspace:{team-B}
```

Resources are linked to workspaces via `t_workspace` tuples. Role bindings are scoped to workspaces via `t_binding`. The workspace `t_parent` relation enables permission inheritance: an admin bound at the org workspace can resolve permissions on all child (team) workspaces.

```mermaid
flowchart LR
    Principal["rbac/principal:redhat/alice"]
    Group["rbac/group:{uuid}"]
    RoleBinding["rbac/role_binding:{id}"]
    Role["rbac/role:cost-openshift-viewer"]
    Workspace["rbac/workspace:{team-uuid}"]
    OrgWorkspace["rbac/workspace:{org_id}"]
    Tenant["rbac/tenant:{org_id}"]
    Resource["cost_management/openshift_cluster:prod"]

    Principal -->|"t_member"| Group
    Group -->|"#member via t_subject"| RoleBinding
    RoleBinding -->|"t_granted"| Role
    Workspace -->|"t_binding"| RoleBinding
    Workspace -->|"t_parent"| OrgWorkspace
    OrgWorkspace -->|"t_parent"| Tenant
    Resource -->|"t_workspace"| Workspace
    Role -->|"t_cost_management_openshift_cluster_read"| AllPrincipals["rbac/principal:*"]
```

**SaaS vs on-prem**: In SaaS, role bindings may be scoped directly to tenants for simplicity (all resources at org level). On-prem uses the workspace layer for team-based access grants. Both models coexist in the same ZED schema — the workspace hierarchy is additive, not a replacement. See the [On-Prem Workspace Management ADR](./onprem-workspace-management-adr.md) and the [ReBAC Bridge Design](./rebac-bridge-design.md) for the full on-prem model.

**ros-ocp-backend note**: ros-ocp-backend performs `CheckPermission` against `rbac/tenant:{orgID}` for wildcard access (e.g., admin with `cost_management_all_all` at org level), and `ListAuthorizedResources` for per-resource access. The `ListAuthorizedResources` path resolves through the full hierarchy (`resource → t_workspace → workspace → t_parent → tenant`), so team-scoped resources are correctly discovered even though the `Check` shortcut targets the tenant.

### 7.7 Schema Upgrade Strategy

- **Additive-only policy**: Schema changes only add new types, relations, or permissions. Never remove or rename existing ones.
- **Tooling**: Schema upgrades are applied via the `zed` CLI as a Helm post-upgrade hook. There are no Django management commands for schema management.

### 7.8 Operational Tooling

Schema management and role seeding are handled by external scripts, not Django management commands:

- **[`deploy-kessel.sh`](../../../dev/kessel/deploy-kessel.sh)** -- applies the ZED schema and seeds roles from `seed-roles.yaml`. Used as Helm post-install/post-upgrade hook.
- **[`kessel-admin.sh`](../../../dev/kessel/kessel-admin.sh)** -- operator tool for managing role bindings, groups, and ad-hoc SpiceDB operations (create/delete bindings, enumerate tuples).

---

## 8. Testing Strategy

A separate [test plan document](./kessel-ocp-test-plan.md) maps every feature to specific test scenarios.

### 8.1 Scenario ID Convention

Format: `{TIER}-{MODULE}-{FEATURE}-{NNN}`

| Segment | Values | Description |
|---------|--------|-------------|
| TIER | `UT`, `IT`, `CT`, `E2E` | Unit, Integration, Contract, End-to-End |
| MODULE | `KESSEL`, `MW`, `SETTINGS`, `MASU`, `API`, `SRC`, `COSTMODEL` | Koku module where the test code lives |
| FEATURE | Short mnemonic (e.g., `AP`, `CL`, `RR`, `AUTH`, `SYNC`, `PB`, `CLEANUP`) | Feature under test |
| NNN | `001`-`999` | Sequential scenario number |

### 8.2 Module Reference

| Code | Koku module | Covers |
|------|-------------|--------|
| `KESSEL` | `koku/koku_rebac/` | access_provider, client, resource_reporter, models, workspace, config, exceptions |
| `MW` | `koku/koku/middleware.py` | Middleware integration (provider dispatch, caching, error handling) |
| `SETTINGS` | `koku/koku/settings.py` | Configuration and startup derivation |
| `MASU` | `koku/masu/` | Pipeline hook (ocp_report_db_accessor sync) |
| `API` | `koku/api/` | ProviderBuilder hook |
| `SRC` | `koku/sources/api/` | Sources API CRUD, CMMO compatibility, Kessel resource lifecycle |
| `COSTMODEL` | `koku/cost_models/` | CostModelViewSet hook |

### 8.3 Per-Scenario Format (IEEE 829-Inspired)

Each test scenario follows a structured format:

| Field | Description |
|-------|-------------|
| **ID** | `{TIER}-{MODULE}-{FEATURE}-{NNN}` |
| **Title** | Short descriptive name |
| **Priority** | P0 (Critical), P1 (High), P2 (Medium), P3 (Low) |
| **Business Value** | 1-2 sentences linking the test to a requirement or risk |
| **Phase** | 1, 1.5, or 2 (maps to DD checkpoint) |
| **Fixtures** | Explicit setup: base class, `@override_settings`, `@patch()`, `baker.make()` |
| **Steps** | BDD format: Given / When / Then |
| **Acceptance Criteria** | Concrete pass/fail conditions |

### 8.4 Priority Levels

| Level | Meaning | Triage guidance |
|-------|---------|-----------------|
| P0 (Critical) | Core contract, blocks all downstream | Must fix immediately; blocks PR merge |
| P1 (High) | Key feature, significant user impact | Fix before phase checkpoint |
| P2 (Medium) | Important but not blocking | Fix before final PR merge |
| P3 (Low) | Defensive, unlikely paths | Can defer to follow-up |

### 8.5 Tier Mapping to Koku Infrastructure

| DD tier | Koku runner | Runs in CI? | Kessel needed? |
|---------|-------------|-------------|----------------|
| Tier 1 (Unit) `UT-*` | Django `manage.py test` / tox | Yes | No (mocked gRPC) |
| Tier 2 (Integration) `IT-*` | Django `manage.py test` with `@override_settings` | Yes | No (mocked gRPC) |
| Tier 3 (Contract) `CT-*` | Django `manage.py test` with Podman Compose Kessel stack | Local only | Yes (real gRPC stack) |
| Tier 4 (E2E) `E2E-*` | IQE plugin with new Kessel markers | No (OCP cluster) | Yes (full stack) |

### 8.6 Coverage Target

Greater than 80% code coverage on the `koku/koku_rebac/` module for unit tier (`UT-*`).

---

## 9. Deployment and Operations

### 9.1 On-Prem Required Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ONPREM` | Yes | `false` | Forces `AUTHORIZATION_BACKEND=rebac` |
| `KESSEL_INVENTORY_HOST` | Yes | `localhost` | Inventory API gRPC host |
| `KESSEL_INVENTORY_PORT` | Yes | `9081` | Inventory API gRPC port |
| `KESSEL_CA_PATH` | No | `""` | Path to CA certificate for TLS; empty = insecure channel |
| `KESSEL_AUTH_ENABLED` | No | `false` | Enable OIDC-based auth for Kessel calls. Defaults to `false` unless `ONPREM=true`, which sets it to `true` automatically |
| `KESSEL_AUTH_CLIENT_ID` | Cond. | `""` | OIDC client ID (required when `KESSEL_AUTH_ENABLED=true`) |
| `KESSEL_AUTH_CLIENT_SECRET` | Cond. | `""` | OIDC client secret (required when `KESSEL_AUTH_ENABLED=true`) |
| `KESSEL_AUTH_OIDC_ISSUER` | Cond. | `""` | OIDC issuer URL (required when `KESSEL_AUTH_ENABLED=true`) |
| `ENHANCED_ORG_ADMIN` | No | `false` | Temporary bootstrap for first admin |
| `KESSEL_CACHE_TIMEOUT` | No | `300` | Access cache timeout in seconds |

### 9.2 Bootstrap Path A -- Gradual (ENHANCED_ORG_ADMIN)

1. Deploy Koku + Kessel/SpiceDB with `ONPREM=true`, `ENHANCED_ORG_ADMIN=true`
2. Seed roles via Helm post-install hook (applies [`seed-roles.yaml`](../../../dev/kessel/seed-roles.yaml) using `deploy-kessel.sh`)
3. First org admin logs in. `ENHANCED_ORG_ADMIN=True` bypasses Kessel -- full access granted
4. Admin creates role bindings for other users via `kessel-admin.sh` or `zed` CLI
5. Set `ENHANCED_ORG_ADMIN=false` and restart. Role bindings now govern access

### 9.3 Bootstrap Path B -- Pre-Configured

1. Deploy Kessel/SpiceDB
2. Seed roles via `deploy-kessel.sh` (applies `seed-roles.yaml`)
3. Pre-load role bindings via `zed` CLI (`zed relationship create`) or Relations API `ImportBulkTuples` (`POST /v1beta1/tuples/bulkimport`)
4. Deploy Koku with `ONPREM=true` only. Users have access from first login

### 9.4 Operational Characteristics

- **Kessel unavailability**: All resource types return no access (empty lists). Users see no data until Kessel recovers — a silent degradation, not an explicit HTTP error. No fallback to RBAC. Monitoring and alerting on Kessel health is essential.
- **No rollback to RBAC on-prem**: RBAC was never deployed. Fix-forward is the only recovery path.
- **Schema upgrades**: Additive-only. Applied via `zed` CLI as a Helm post-upgrade hook.

### 9.5 SaaS Future Wiring (Documented Hook Only)

Koku uses Unleash for feature flags via `UnleashClient` (see [`koku/koku/feature_flags.py`](../../../koku/koku/feature_flags.py)). The existing pattern uses `UNLEASH_CLIENT.is_enabled(flag_name, context)` with per-account context.

When SaaS is ready for per-org Kessel rollout, the hook point is in `get_access_provider()`:

```python
def get_access_provider(org_id=None) -> AccessProvider:
    if settings.AUTHORIZATION_BACKEND == "rebac":
        return KesselAccessProvider()
    # Future SaaS hook: per-org Unleash override
    # if org_id and is_feature_flag_enabled_by_account(
    #     org_id, "cost-management.backend.enable-kessel-rebac"
    # ):
    #     return KesselAccessProvider()
    return RBACAccessProvider()
```

This follows the existing Unleash pattern used throughout Koku (e.g., `cost-management.backend.ocp_gpu_cost_model` in [`masu/processor/__init__.py`](../../../koku/masu/processor/__init__.py#L27)). Implementation is deferred -- only the hook point is documented.

---

## 10. Dependencies

### 10.1 Python Packages

Added to `Pipfile`:

| Package | Purpose | Used by |
|---------|---------|---------|
| `kessel-sdk` | Inventory API client (gRPC) -- `StreamedListObjects`, `Check`, `ReportResource`, `DeleteResource` | `KesselAccessProvider`, `ResourceReporter` |
| `grpcio` | gRPC runtime | Transitive dep, explicit in Pipfile |

### 10.2 Inventory API Client

Source: [project-kessel/kessel-sdk-py](https://github.com/project-kessel/kessel-sdk-py)

Key methods on `KesselInventoryServiceStub`:
- `StreamedListObjects` -- list resources the principal has a given permission on (used for scoped `read` access)
- `Check` -- verify a single principal-resource-permission tuple (used for wildcard / `write` access checks)
- `ReportResource` -- report resource existence to Kessel Inventory
- `DeleteResource` -- remove resource from Kessel Inventory (used for resource lifecycle cleanup)

### 10.3 External Schema Dependency (Blocking)

The production ZED schema in [`rbac-config`](https://github.com/RedHatInsights/rbac-config) (`configs/prod/schemas/schema.zed`) defines 23 `cost_management_*` permissions on `rbac/role` but does **not** propagate them through `rbac/role_binding` or `rbac/tenant`. This means `StreamedListObjects()` and `Check()` cannot evaluate cost management permissions even when role bindings exist.

**Scope: All 23 permissions (13 OCP + 10 cloud).** The PR wires all cost_management permissions so Koku and SaaS are ready when SaaS onboards Kessel. Cloud permissions (AWS, Azure, GCP) are included in the same PR.

**Jira:** [FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319)

**Required changes** (PR to [`RedHatInsights/rbac-config`](https://github.com/RedHatInsights/rbac-config)): Wire all 23 permissions through `rbac/role_binding` and `rbac/tenant`. Copy-paste-ready ZED (including the 10 cloud permissions) is in [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md) Section 2, Gap G-1.

1. `rbac/role_binding` -- add 23 permission arrows using the existing pattern `(subject & t_granted->X)` (13 OCP + 10 cloud; see delta doc for full block):
   ```zed
   definition rbac/role_binding {
       // ... existing permissions for other services ...
       permission cost_management_all_all = (subject & t_granted->cost_management_all_all)
       permission cost_management_openshift_cluster_all = (subject & t_granted->cost_management_openshift_cluster_all)
       permission cost_management_openshift_cluster_read = (subject & t_granted->cost_management_openshift_cluster_read)
       permission cost_management_openshift_node_all = (subject & t_granted->cost_management_openshift_node_all)
       permission cost_management_openshift_node_read = (subject & t_granted->cost_management_openshift_node_read)
       permission cost_management_openshift_project_all = (subject & t_granted->cost_management_openshift_project_all)
       permission cost_management_openshift_project_read = (subject & t_granted->cost_management_openshift_project_read)
       permission cost_management_cost_model_all = (subject & t_granted->cost_management_cost_model_all)
       permission cost_management_cost_model_read = (subject & t_granted->cost_management_cost_model_read)
       permission cost_management_cost_model_write = (subject & t_granted->cost_management_cost_model_write)
       permission cost_management_settings_all = (subject & t_granted->cost_management_settings_all)
       permission cost_management_settings_read = (subject & t_granted->cost_management_settings_read)
       permission cost_management_settings_write = (subject & t_granted->cost_management_settings_write)
   }
   ```

2. `rbac/tenant` -- add 23 permission arrows using the existing pattern `t_binding->X + t_platform->X` (13 OCP + 10 cloud; see delta doc for full block):
   ```zed
   definition rbac/tenant {
       // ... existing permissions for other services ...
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
   }
   ```

Until this PR lands, the E2E flow (`principal -> role_binding -> role -> tenant -> resource`) will not resolve for cost management permissions. Unit and integration tests (which mock gRPC) are unaffected.

**Additional gaps identified**: Beyond the wiring gap, there are permission naming divergences and missing `_all` verb permissions between our local schema and upstream. See [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md) for the full delta tracking, comparison matrix, and reconciliation plan.

### 10.4 External Tooling (Operator Use)

- `zed` CLI -- SpiceDB schema writes, relationship creation, backup/restore (Bootstrap Path B)
- Relations API REST -- `ImportBulkTuples` (`POST /v1beta1/tuples/bulkimport`) for bulk pre-loading

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **ZED schema gap: cost_management permissions not wired through role_binding/tenant** | `StreamedListObjects` / `Check` will not return results even with correct role bindings because the authorization chain is incomplete | [FLPATH-3319](https://issues.redhat.com/browse/FLPATH-3319): Submit PR to `rbac-config` adding all 23 `cost_management_*` permissions (13 OCP + 10 cloud) through `rbac/role_binding` and `rbac/tenant`. Full delta and copy-paste ZED in [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md). **Blocking external dependency** |
| ~~**ZED schema naming divergence**~~ | ~~Local schema used abbreviated permission names~~ | **Resolved**: All local names aligned to upstream convention (G-2). See [delta doc](./zed-schema-upstream-delta.md#g-2-permission-naming-divergence) |
| **gRPC in Django WSGI process** | Thread-safety concerns with gRPC channels | Lazy singleton with `threading.Lock`; verify in load tests |
| **Performance: many Inventory API calls** | Up to 11 workspace `Check` calls + up to 11 `StreamedListObjects` fallback calls = minimum 11, maximum 22 gRPC calls per cache miss (derived from 11 types in `KOKU_TO_KESSEL_TYPE_MAP`) | Cache aggressively (300s default); workspace checks short-circuit `StreamedListObjects` for users with org-wide roles |
| **Inventory API gRPC failure** | Any resource type query fails mid-request | Fail-open per-type: `_check_workspace_permission` / `_streamed_list_objects` catch all exceptions and return `False` / `[]`. The failing type returns no access; other types proceed normally. `KesselConnectionError` is defined but currently unused — the middleware handler exists as a safety net for future explicit raises. See Section 5.1 |
| **Kessel unavailability** | All types return no access (empty lists) | Users see no data until Kessel recovers; no HTTP 424. Monitoring required to detect silent degradation |
| **No RBAC rollback on-prem** | Cannot fall back to RBAC | Fix-forward only; documented in operations guide |
| **SaaS future wiring** | Unleash integration not yet implemented | Documented as hook point in `get_access_provider()` |
| **Large ID lists in WHERE IN** | Performance degradation for users with access to many resources | Acceptable trade-off; optimize with query-layer awareness later |

---

## Appendix A: Files to Create/Modify

### New Files

All in new `koku/koku_rebac/` Django app:

- `koku/koku_rebac/__init__.py`
- `koku/koku_rebac/apps.py` -- Django app configuration
- `koku/koku_rebac/config.py` -- `resolve_authorization_backend()` logic
- `koku/koku_rebac/models.py` -- `KesselSyncedResource`
- `koku/koku_rebac/access_provider.py` -- `RBACAccessProvider`, `KesselAccessProvider`, `get_access_provider()`
- `koku/koku_rebac/resource_reporter.py` -- transparent resource reporting
- `koku/koku_rebac/client.py` -- Kessel Inventory API v1beta2 gRPC client wrapper (lazy singleton)
- `koku/koku_rebac/workspace.py` -- workspace resolution (`ShimResolver` for on-prem, `RbacV2Resolver` for SaaS)
- `koku/koku_rebac/exceptions.py` -- `KesselConnectionError`
- `koku/koku_rebac/urls.py` -- empty (management endpoints externalized to `kessel-admin.sh`)

### Modified Files

- `koku/koku/settings.py` -- `AUTHORIZATION_BACKEND`, `KESSEL_INVENTORY_CONFIG`, `KESSEL_CA_PATH`, `KESSEL_AUTH_*`, `CacheEnum.kessel`, cache entry, app registration
- `koku/koku/middleware.py` -- use `AccessProvider`, dual cache key, `KesselConnectionError` handling, settings sentinel hook
- `koku/api/provider/provider_builder.py` -- `on_resource_created()` call in `create_provider_from_source()`
- `koku/masu/database/ocp_report_db_accessor.py` -- `on_resource_created()` calls in `populate_openshift_cluster_information_tables()`
- `koku/cost_models/view.py` -- `on_resource_created()` call in `perform_create()`
- `Pipfile` -- add `kessel-sdk`, `grpcio`

### Unchanged Files

- `koku/api/common/permissions/*.py` -- permission classes already handle both wildcard and granular ID lists
- `koku/api/query_params.py` -- `_set_access()` already filters by specific IDs
- `koku/api/query_handler.py` -- `set_access_filters()` already applies ID-based filters
- `koku/api/resource_types/*/view.py` -- all resource type views already filter by specific IDs
- `koku/cost_models/view.py` `get_queryset()` -- already does `filter(uuid__in=read_access_list)`
- `koku/koku/rbac.py` -- `RbacService` unchanged, wrapped by `RBACAccessProvider`

---

## Appendix B: Kessel gRPC Client Wrapper

File: [`koku/koku_rebac/client.py`](../../../koku/koku_rebac/client.py)

The client wraps a single gRPC stub for the Kessel Inventory API v1beta2. All authorization
checks (`Check`, `StreamedListObjects`) and resource reporting (`ReportResource`) go through
this stub. The Relations API is not used by production code.

From [`client.py`](../../../koku/koku_rebac/client.py):

```python
class KesselClient:
    """Wraps the Kessel Inventory API v1beta2 gRPC stub.

    This is the only Kessel client Koku needs -- all authorization
    checks (Check, StreamedListObjects) and resource reporting
    (ReportResource) go through the Inventory API.
    """

    def __init__(self) -> None:
        inventory_cfg: dict = settings.KESSEL_INVENTORY_CONFIG
        ca_path: str = getattr(settings, "KESSEL_CA_PATH", "")

        self._channel = self._build_channel(inventory_cfg, ca_path)
        self.inventory_stub = inventory_service_pb2_grpc.KesselInventoryServiceStub(self._channel)

    @staticmethod
    def _build_channel(config: dict, ca_path: str) -> grpc.Channel:
        target = f"{config['host']}:{config['port']}"
        call_creds = get_grpc_call_credentials()

        if ca_path:
            channel_creds = _build_channel_credentials(ca_path)
            if call_creds:
                channel_creds = grpc.composite_channel_credentials(channel_creds, call_creds)
            return grpc.secure_channel(target, channel_creds)

        if call_creds:
            channel_creds = grpc.composite_channel_credentials(
                grpc.local_channel_credentials(), call_creds
            )
            return grpc.secure_channel(target, channel_creds)

        return grpc.insecure_channel(target)


def get_kessel_client() -> KesselClient:
    """Return (or create) the process-wide singleton KesselClient.

    Uses double-checked locking to avoid acquiring the lock on every call.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = KesselClient()
                LOG.info(log_json(msg="KesselClient initialised (Inventory API v1beta2 only)"))
    return _client_instance
```
    global _client_instance
    with _client_lock:
        _client_instance = None
```
