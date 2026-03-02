# Kessel/ReBAC Integration -- Retired Test Scenarios

This file contains the full text of retired test scenarios from the
[Kessel/ReBAC Integration Test Plan](./kessel-ocp-test-plan.md).

These scenarios were retired during the Inventory API v1beta2 migration
when the management plane was externalized to `kessel-admin.sh` and direct
Relations API / LookupResources usage was removed from Koku.

---

## Tier 1 -- Retired Unit Tests (UT)

---

### UT-KESSEL-SEED-001: Role seeding command is safe to run in RBAC environments

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Helm charts run management commands unconditionally; the command must be harmless in SaaS RBAC deployments where Kessel does not exist |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rbac")`

**Steps:**
- **Given** a SaaS deployment configured with RBAC authorization (no Kessel available)
- **When** the `kessel_seed_roles` management command is executed (e.g., as a Helm post-install hook)
- **Then** the command completes successfully without attempting any Kessel connections or creating any roles

**Acceptance Criteria:**
- The command exits cleanly with a skip message
- No gRPC connections are attempted (Kessel may not even be deployed)
- The command can be run repeatedly in RBAC environments without side effects

---

### UT-KESSEL-SEED-002: All 5 SaaS production roles are created in Kessel

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | Administrators must be able to assign the same 5 roles available in SaaS production. Missing roles means admins cannot grant the expected access levels |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client that records `create_tuples` calls

**Steps:**
- **Given** a ReBAC deployment during initial setup
- **When** the `kessel_seed_roles` command is executed with default (embedded) role definitions
- **Then** all 5 standard Cost Management roles from SaaS production are created in Kessel

**Acceptance Criteria:**
- Exactly 5 roles are seeded: Cost Administrator (`cost-administrator`), Cost OpenShift Viewer (`cost-openshift-viewer`), Cost Price List Administrator (`cost-price-list-administrator`), Cost Price List Viewer (`cost-price-list-viewer`), Cost Cloud Viewer (`cost-cloud-viewer`)
- Running the command a second time succeeds without errors (idempotent via upsert)
- The roles match the definitions in `RedHatInsights/rbac-config/configs/prod/roles/cost-management.json`

---

### UT-KESSEL-SEED-003: Cost Administrator role grants access to all cost management resource types

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | A Cost Administrator must have full access to every cost management resource type. If any permission is missing, admins silently lose access to that resource type |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment during role seeding
- **When** the `kessel_seed_roles` command creates the Cost Administrator role
- **Then** the role is granted all 23 cost_management permissions from the production ZED schema, covering every resource type (OCP clusters/nodes/projects, AWS accounts/OUs, Azure subscriptions, GCP accounts/projects, cost models, settings)

**Acceptance Criteria:**
- The Cost Administrator role has exactly 23 permission relations matching the production `rbac/role` schema
- The role covers all resource types: OCP (6 relations), AWS (4), Azure (2), GCP (4), cost model (3), settings (3), plus the global `all_all` (1)
- A user assigned this role can access cost data for every resource type through `LookupResources`

---

### UT-KESSEL-SEED-004: Cost OpenShift Viewer role grants only OCP cluster access

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | The OCP viewer role must be scoped to OCP clusters only; granting cloud or settings access would violate the principle of least privilege |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment during role seeding
- **When** the `kessel_seed_roles` command creates the Cost OpenShift Viewer role
- **Then** the role is granted only OCP cluster read and all permissions, and no permissions for cloud providers, cost models, or settings

**Acceptance Criteria:**
- The role has exactly 2 permission relations: `t_cost_management_openshift_cluster_all` and `t_cost_management_openshift_cluster_read`
- A user assigned this role can see OCP cluster cost data but cannot access AWS, Azure, GCP, cost model, or settings data

---

### UT-KESSEL-SEED-005: Every RBAC permission string from SaaS role definitions has a Kessel mapping

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | An unmapped RBAC permission means that role grants no Kessel access for the affected resource type, silently breaking authorization for users with that role |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** the SaaS production role definitions contain 11 unique RBAC permission strings across 5 roles
- **When** the permission mapping constant is validated against all role definitions
- **Then** every RBAC permission string resolves to at least one Kessel relation

**Acceptance Criteria:**
- All 11 RBAC permission patterns are mapped: `cost-management:*:*`, `cost-management:cost_model:*`, `cost-management:cost_model:read`, `cost-management:settings:*`, `cost-management:settings:read`, `cost-management:openshift.cluster:*`, `cost-management:aws.account:*`, `cost-management:aws.organizational_unit:*`, `cost-management:azure.subscription_guid:*`, `cost-management:gcp.account:*`, `cost-management:gcp.project:*`
- No RBAC permission string from any role causes a lookup failure during seeding

---

### UT-KESSEL-SEED-006: Air-gapped deployments can seed roles from a local file

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P2 (Medium) |
| Business Value | On-prem environments without internet access must be able to seed roles from a file shipped with the deployment, rather than fetching from GitHub |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client
- Temporary JSON file with `cost-management.json` content

**Steps:**
- **Given** an air-gapped on-prem deployment with a local copy of the role definitions file
- **When** `kessel_seed_roles --roles-file /path/to/cost-management.json` is executed
- **Then** roles are loaded from the local file and seeded with the same permission mappings as the embedded defaults

**Acceptance Criteria:**
- The command reads role definitions from the specified file path
- The same 5 roles with identical permission mappings are created as with the embedded defaults
- No network requests are made to GitHub or any external service

---

### UT-KESSEL-SCHEMA-001: Helm upgrade hooks do not apply redundant schema changes

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_update_schema.py` deleted; schema management externalized to `kessel-admin.sh` |
| Priority | P2 (Medium) |
| Business Value | Schema migrations are sensitive operations; running them unnecessarily risks data corruption or downtime |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.management.commands.kessel_update_schema.CURRENT_SCHEMA_VERSION", "1")` matching deployed version

**Steps:**
- **Given** the Kessel schema is already at the target version (hardcoded `CURRENT_SCHEMA_VERSION`)
- **When** the `kessel_update_schema` command runs (e.g., during a Helm upgrade)
- **Then** the command detects the schema is current and completes without applying any migrations

**Acceptance Criteria:**
- The command skips migration when the deployed version matches the target
- No schema modification calls are made to Kessel
- The command can be run repeatedly without side effects

---

### UT-KESSEL-VIEW-001: Administrators can see available roles for assignment

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators must know which roles exist before they can assign them to users; without a role listing, role binding creation is a guessing game |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` returning mock with 5 seeded roles

**Steps:**
- **Given** a ReBAC deployment where the 5 standard Cost Management roles have been seeded
- **When** an administrator requests the list of available roles via the Access Management API
- **Then** all 5 roles are returned with their names and permission descriptions

**Acceptance Criteria:**
- The API response includes all 5 production roles (Cost Administrator, Cost OpenShift Viewer, Cost Price List Administrator, Cost Price List Viewer, Cost Cloud Viewer)
- Each role includes enough information for the administrator to make an informed assignment decision
- The response is HTTP 200

---

### UT-KESSEL-VIEW-002: Assigning a role to a user takes effect immediately

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When an admin assigns a role to a user, that user must see the authorized data on their very next request -- not after a cache TTL expires |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client
- `@patch("django.core.cache.caches")` with mock cache

**Steps:**
- **Given** an administrator assigning the Cost OpenShift Viewer role to user `alice` in org `org123`
- **When** the role binding is created via the Access Management API
- **Then** the role binding is written to Kessel and alice's cached access is invalidated so her next request fetches fresh permissions

**Acceptance Criteria:**
- The role binding relationship is created in Kessel (subject=alice, role=cost-openshift-viewer, scope=org123)
- Alice's cached authorization data is purged, forcing a fresh `LookupResources` on her next request
- The API returns HTTP 201 confirming the binding was created

---

### UT-KESSEL-VIEW-003: Revoking a role from a user takes effect immediately

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When an admin revokes access, the user must lose access on their very next request -- delayed revocation is a security risk |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client
- `@patch("django.core.cache.caches")` with mock cache

**Steps:**
- **Given** user `alice` has a Cost OpenShift Viewer role binding in org `org123`
- **When** an administrator revokes that role binding via the Access Management API
- **Then** the role binding is removed from Kessel and alice's cached access is invalidated so her next request reflects the revocation

**Acceptance Criteria:**
- The role binding relationship is deleted from Kessel
- Alice's cached authorization data is purged immediately
- Alice's next request results in a fresh `LookupResources` that no longer includes the revoked role's permissions
- The API returns HTTP 204 confirming the deletion

---

### UT-KESSEL-SEED-007: Role seeding command supports dry-run mode for safe validation

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_seed_roles.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P2 (Medium) |
| Business Value | Operators must be able to validate what roles will be seeded before committing to a live Kessel instance, especially in production environments |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client

**Steps:**
- **Given** a ReBAC deployment where the operator wants to preview the role seeding
- **When** `kessel_seed_roles --dry-run` is executed
- **Then** the command outputs the roles and permissions that would be created, but makes no Kessel API calls

**Acceptance Criteria:**
- The command output lists all 5 roles with their permission mappings
- No `create_tuples` calls are made to Kessel
- The operator can use the output to verify correct configuration before running for real

---

### UT-KESSEL-SCHEMA-002: Schema update command applies migrations when version is behind

| Field | Value |
|-------|-------|
| Status | RETIRED — `kessel_update_schema.py` deleted; schema management externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | When a new Kessel schema version is deployed, the update command must apply the migration. If it silently skips, the schema is out of date and authorization queries may fail |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.management.commands.kessel_update_schema.CURRENT_SCHEMA_VERSION", "2")` while deployed version is `"1"`

**Steps:**
- **Given** the deployed schema is at version 1 and the hardcoded `CURRENT_SCHEMA_VERSION` is 2
- **When** the `kessel_update_schema` command runs
- **Then** the schema migration from version 1 to version 2 is applied to Kessel

**Acceptance Criteria:**
- The migration is applied and the deployed version is updated to 2
- The command logs the migration that was applied for audit purposes
- If the migration fails, the error is reported clearly (not swallowed)

---

### UT-KESSEL-VIEW-004: Administrators can list existing role bindings

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators need to see who has what access to audit and manage permissions. Without a listing endpoint, they cannot verify or troubleshoot access issues |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.client.get_kessel_client")` with mock client returning 3 role bindings

**Steps:**
- **Given** a ReBAC deployment with 3 existing role bindings (2 users with Cost OpenShift Viewer, 1 with Cost Administrator)
- **When** an administrator requests the list of role bindings via `GET /api/cost-management/v1/access-management/role-bindings/`
- **Then** all 3 bindings are returned with user, role, and scope information

**Acceptance Criteria:**
- The response includes the subject (user), role name, and scope for each binding
- The list is scoped to the administrator's organization
- The response is HTTP 200

---

### UT-KESSEL-GRP-001: Create a group in Kessel

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators must be able to create groups to assign roles to teams rather than individual users, matching RBAC group functionality |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `APIRequestFactory` for POST request

**Steps:**
- **Given** a ReBAC deployment where an administrator needs to create a group for a team of OCP viewers
- **When** the administrator POSTs to `/api/cost-management/v1/access-management/groups/` with `{"slug": "ocp-viewers", "name": "OCP Viewers", "org_id": "org123"}`
- **Then** the group is created in Kessel as an `rbac/group` resource with an `t_owner` relation to the tenant

**Acceptance Criteria:**
- `CreateTuples` is called with a tuple linking `rbac/group:ocp-viewers` to `rbac/tenant:org123` via `t_owner`
- The API returns HTTP 201 with the group data
- The group exists in Kessel for subsequent role binding operations

---

### UT-KESSEL-GRP-002: List groups from Kessel

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators must be able to see existing groups to manage team-based access control |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` returning mock with 2 groups
- `APIRequestFactory` for GET request

**Steps:**
- **Given** a ReBAC deployment with 2 existing groups (`ocp-viewers`, `cost-admins`)
- **When** an administrator requests the list of groups via `GET /api/cost-management/v1/access-management/groups/`
- **Then** both groups are returned with their slug, name, and org information

**Acceptance Criteria:**
- The response includes both groups with their slugs
- The response is HTTP 200
- Groups are read from Kessel via `ReadTuples` filtering on `rbac/group` resource type

---

### UT-KESSEL-GRP-003: Delete a group from Kessel

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators must be able to remove groups that are no longer needed to maintain clean access control |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `APIRequestFactory` for DELETE request

**Steps:**
- **Given** a group `ocp-viewers` exists in Kessel
- **When** an administrator sends `DELETE /api/cost-management/v1/access-management/groups/ocp-viewers/`
- **Then** the group is removed from Kessel via `DeleteTuples`

**Acceptance Criteria:**
- `DeleteTuples` is called with a filter matching the group's resource
- The API returns HTTP 204
- Subsequent list calls no longer include the deleted group

---

### UT-KESSEL-GRP-004: Add a principal to a group

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | Group membership is the core mechanism for team-based access; without the ability to add members, groups are unusable |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `APIRequestFactory` for POST request

**Steps:**
- **Given** a group `ocp-viewers` exists in Kessel
- **When** an administrator adds user `alice` to the group via `POST /api/cost-management/v1/access-management/groups/ocp-viewers/members/` with `{"principal": "alice"}`
- **Then** a `t_member` relation is created linking `rbac/principal:alice` to `rbac/group:ocp-viewers`

**Acceptance Criteria:**
- `CreateTuples` is called with a relationship: resource=`rbac/group:ocp-viewers`, relation=`t_member`, subject=`rbac/principal:alice`
- The API returns HTTP 201
- Alice inherits any role bindings assigned to the group

---

### UT-KESSEL-GRP-005: Remove a principal from a group

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When a team member leaves or changes roles, their group membership must be revocable to ensure proper access control |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `APIRequestFactory` for DELETE request

**Steps:**
- **Given** user `alice` is a member of group `ocp-viewers`
- **When** an administrator removes alice from the group via `DELETE /api/cost-management/v1/access-management/groups/ocp-viewers/members/alice/`
- **Then** the `t_member` relation between alice and the group is deleted from Kessel

**Acceptance Criteria:**
- `DeleteTuples` is called with a filter removing the membership relationship
- The API returns HTTP 204
- Alice no longer inherits role bindings from the group on her next request

---

### UT-KESSEL-GRP-006: Adding a member invalidates that member's cache

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When a user is added to a group with existing role bindings, their cached access must be invalidated so they see their new permissions on the next request |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `@patch("koku_rebac.views._invalidate_user_cache")`

**Steps:**
- **Given** group `ocp-viewers` has a role binding for Cost OpenShift Viewer
- **When** user `alice` is added to the group
- **Then** alice's cached authorization data is invalidated

**Acceptance Criteria:**
- `_invalidate_user_cache("alice")` is called
- Alice's next request triggers a fresh `LookupResources` that includes the group's role binding

---

### UT-KESSEL-GRP-007: Removing a member invalidates that member's cache

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When a user is removed from a group, their cached access must be invalidated immediately so they lose the group's permissions on the next request -- delayed revocation is a security risk |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `@patch("koku_rebac.views._invalidate_user_cache")`

**Steps:**
- **Given** user `alice` is a member of group `ocp-viewers` with a Cost OpenShift Viewer role binding
- **When** alice is removed from the group
- **Then** alice's cached authorization data is invalidated

**Acceptance Criteria:**
- `_invalidate_user_cache("alice")` is called
- Alice's next request triggers a fresh `LookupResources` that no longer includes the group's permissions

---

### UT-KESSEL-GRP-008: Binding a role to a group invalidates all members' caches

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When a role is bound to a group, all members must see updated access on their next request. If only the group principal's cache is cleared, individual members continue with stale permissions |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client returning 3 members via `ReadTuples`
- `@patch("koku_rebac.views._invalidate_user_cache")`

**Steps:**
- **Given** users Alice, Bob, and Carol are members of group `ocp-viewers`
- **When** the Cost OpenShift Viewer role is bound to the group (subject_type="group")
- **Then** cached access for all 3 members is invalidated

**Acceptance Criteria:**
- `_invalidate_user_cache` is called for "alice", "bob", and "carol"
- Each member's next request triggers a fresh `LookupResources` reflecting the new role binding
- The group's role binding tuple uses `rbac/group#member` as the subject type

---

### UT-KESSEL-GRP-009: Unbinding a role from a group invalidates all members' caches

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | When a role is revoked from a group, all members must lose the revoked permissions immediately -- delayed revocation for any member is a security risk |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@patch("koku_rebac.views.get_kessel_client")` with mock client returning 2 members via `ReadTuples`
- `@patch("koku_rebac.views._invalidate_user_cache")`

**Steps:**
- **Given** users Alice and Bob are members of group `ocp-viewers` with a Cost OpenShift Viewer role binding
- **When** the role binding is deleted from the group
- **Then** cached access for both members is invalidated

**Acceptance Criteria:**
- `_invalidate_user_cache` is called for "alice" and "bob"
- Each member's next request triggers a fresh `LookupResources` that no longer includes the revoked role's permissions

---

### UT-KESSEL-GRP-010: Role binding serializer accepts subject_type "group"

| Field | Value |
|-------|-------|
| Status | RETIRED — `serializers.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | The API must distinguish between binding a role to a user vs a group; without subject_type validation, group bindings cannot be expressed |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class

**Steps:**
- **Given** an API request to bind a role to a group
- **When** the `RoleBindingSerializer` receives `{"role_slug": "cost-openshift-viewer", "principal": "ocp-viewers", "org_id": "org123", "subject_type": "group"}`
- **Then** the serializer validates successfully with `subject_type` set to `"group"`

**Acceptance Criteria:**
- The serializer accepts `subject_type` with valid choices `"principal"` and `"group"`
- The validated data includes `subject_type: "group"`

---

### UT-KESSEL-GRP-011: Role binding serializer defaults subject_type to "principal"

| Field | Value |
|-------|-------|
| Status | RETIRED — `serializers.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Existing role binding creation calls that do not pass subject_type must continue working as-is, maintaining backward compatibility |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class

**Steps:**
- **Given** an API request to bind a role to a user without specifying subject_type
- **When** the `RoleBindingSerializer` receives `{"role_slug": "cost-admin", "principal": "alice", "org_id": "org123"}`
- **Then** the serializer validates successfully with `subject_type` defaulting to `"principal"`

**Acceptance Criteria:**
- The serializer accepts requests without `subject_type`
- The validated data includes `subject_type: "principal"` (default)
- Backward compatibility is maintained with existing callers

---

### UT-KESSEL-GRP-012: Group CRUD is hidden when AUTHORIZATION_BACKEND is rbac

| Field | Value |
|-------|-------|
| Status | RETIRED — `views.py` deleted; group CRUD externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | SaaS RBAC deployments manage groups through the RBAC service; exposing the Kessel group API would confuse administrators and create a security surface |
| Phase | 1.5 |

**Fixtures:**
- `SimpleTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rbac")`

**Steps:**
- **Given** a SaaS deployment using RBAC authorization
- **When** a request is made to any group management endpoint
- **Then** the endpoint does not exist (HTTP 404), as if it was never registered

**Acceptance Criteria:**
- The URL patterns for group management are not registered in the RBAC configuration
- Requesting any group endpoint returns 404
- No Kessel group API surface is exposed in RBAC deployments

---

### UT-KESSEL-AP-007: OCP inheritance replicates RBAC cascade -- cluster access grants node and project access

| Field | Value |
|-------|-------|
| Status | RETIRED — `_apply_ocp_inheritance()` removed; OCP inheritance now handled by ZED schema permission formulas |
| Priority | P0 (Critical) |
| Business Value | RBAC grants wildcard node and project access to users with cluster access. If Kessel does not replicate this cascade, users with cluster-level roles lose node and project visibility, breaking RBAC parity |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class
- `@patch("koku_rebac.client.get_kessel_client")` returning `["cluster-1"]` for cluster lookup, `[]` for node and project lookups
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a user with a role binding that grants `openshift.cluster:read` for `cluster-1`, but no explicit node or project bindings
- **When** `KesselAccessProvider` resolves the user's access
- **Then** the user has access to cluster `cluster-1` AND wildcard access to all nodes and all projects within that cluster (replicating RBAC's cascade behavior)

**Acceptance Criteria:**
- Cluster access automatically implies node and project access (downward cascade)
- The cascade matches `rbac.py` `_update_access_obj()` logic: cluster -> wildcard node -> wildcard project
- Node access does NOT cascade upward to cluster access

---

### UT-KESSEL-RR-005: Resource type names use Kessel naming convention, not Koku RBAC convention

| Field | Value |
|-------|-------|
| Status | RETIRED — naming convention validation superseded by UT-KESSEL-AP-004 update (type mapping coverage) |
| Priority | P1 (High) |
| Business Value | Koku/RBAC uses dots in resource types (e.g., `openshift.cluster`) while Kessel uses underscores (e.g., `openshift_cluster`). If the reporter sends the wrong format, Kessel rejects or misroutes the resource |
| Phase | 1 |

**Fixtures:**
- `TestCase` base class

**Steps:**
- **Given** Koku's `RESOURCE_TYPES` uses dots (e.g., `openshift.cluster`) and Kessel Inventory expects underscores (e.g., `cost_management/openshift_cluster`)
- **When** the resource reporter maps a Koku resource type to a Kessel type
- **Then** the mapping correctly translates dots to the Kessel naming convention

**Acceptance Criteria:**
- Every resource type in `KOKU_TO_KESSEL_TYPE_MAP` correctly maps from dot notation to underscore notation
- The reporter never sends dot-notation types to Kessel APIs

---

## Tier 2 -- Retired Integration Tests (IT)

---

### IT-API-URL-001: Access Management API is available in ReBAC deployments

| Field | Value |
|-------|-------|
| Status | RETIRED — access management URLs removed; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Administrators in on-prem (ReBAC) deployments need the Access Management API to list roles and manage role bindings; without it, access control cannot be configured |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`

**Steps:**
- **Given** a ReBAC deployment
- **When** an administrator navigates to the Access Management API endpoints (roles, role-bindings)
- **Then** the endpoints are reachable and respond with valid data or appropriate authorization errors

**Acceptance Criteria:**
- `/api/cost-management/v1/access-management/roles/` returns a 200 response with role data
- The endpoints are not hidden behind a feature flag (always available when ReBAC is active)
- Unauthenticated requests are rejected with 401, not 404

---

### IT-API-URL-002: Access Management API is hidden in RBAC deployments

| Field | Value |
|-------|-------|
| Status | RETIRED — access management URLs removed; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | SaaS RBAC deployments manage roles through the RBAC service; exposing the Kessel Access Management API would confuse administrators and create a security surface |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rbac")`

**Steps:**
- **Given** a SaaS deployment using RBAC authorization
- **When** a request is made to any Access Management API endpoint
- **Then** the endpoint does not exist (HTTP 404), as if it was never registered

**Acceptance Criteria:**
- The URL patterns for Access Management are not registered in the RBAC configuration
- Requesting any Access Management endpoint returns 404
- No Kessel-specific API surface is exposed in RBAC deployments

---

### IT-API-URL-003: Access Management API returns role data through full DRF cycle

| Field | Value |
|-------|-------|
| Status | RETIRED — access management URLs removed; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | The roles endpoint must work end-to-end through DRF serialization, not just at the view level -- validates URL routing, permissions, and serialization together |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.views.get_kessel_client")` returning mock with 2 roles
- `APIClient` with valid identity headers

**Steps:**
- **Given** a ReBAC deployment with 2 roles seeded in Kessel
- **When** an administrator makes a GET request to `/api/cost-management/v1/access-management/roles/` through the Django test client
- **Then** the response is HTTP 200 with serialized role data including slug, name, and relations

**Acceptance Criteria:**
- The full HTTP request -> DRF routing -> view -> serialization -> response cycle works
- Response data matches the roles returned by the Kessel mock
- DRF serialization produces valid JSON with expected fields

---

### IT-API-URL-004: Role binding creation through full DRF cycle invalidates cache

| Field | Value |
|-------|-------|
| Status | RETIRED — access management URLs removed; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Role binding creation must trigger cache invalidation end-to-end through the DRF cycle, not just when tested at the view level |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.views.get_kessel_client")` with mock client
- `@override_settings(CACHES={CacheEnum.kessel: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})` for real cache testing
- `APIClient` with valid identity headers

**Steps:**
- **Given** a ReBAC deployment where the Kessel cache is primed with authorization data for user `alice`
- **When** a role binding is created for `alice` via POST to `/api/cost-management/v1/access-management/role-bindings/`
- **Then** alice's cached authorization data is purged from the Kessel cache

**Acceptance Criteria:**
- The full HTTP request -> DRF routing -> view -> CreateTuples -> cache invalidation cycle works
- The Kessel cache no longer contains alice's authorization data after the binding is created
- The API returns HTTP 201

---

### IT-API-URL-005: Group role binding through full DRF cycle invalidates all members

| Field | Value |
|-------|-------|
| Status | RETIRED — access management URLs removed; management plane externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | When a role is bound to a group via the API, all group members must have their caches invalidated, tested end-to-end through the DRF cycle |
| Phase | 1.5 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.views.get_kessel_client")` returning mock with 3 group members via ReadTuples
- `@override_settings(CACHES={CacheEnum.kessel: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})` for real cache testing
- `APIClient` with valid identity headers

**Steps:**
- **Given** a ReBAC deployment where group `ocp-viewers` has members Alice, Bob, and Carol, and all 3 have cached authorization data
- **When** a role binding is created for the group via POST to `/api/cost-management/v1/access-management/role-bindings/` with `subject_type=group`
- **Then** the Kessel cache no longer contains authorization data for any of the 3 group members

**Acceptance Criteria:**
- The full POST -> CreateTuples -> ReadTuples (group members) -> cache invalidation fan-out cycle works
- All 3 members have their cached authorization purged
- The API returns HTTP 201

---

### IT-MW-AUTH-009: Backend switching between RBAC and ReBAC is clean

| Field | Value |
|-------|-------|
| Status | RETIRED — backend switching test obsolete; no shared views between backends after management plane externalization |
| Priority | P1 (High) |
| Business Value | When switching from RBAC to ReBAC (or vice versa), stale cache entries from the previous backend must not be served |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings` for switching between `AUTHORIZATION_BACKEND="rbac"` and `"rebac"`

**Steps:**
- **Given** authorization data cached under the RBAC backend
- **When** the backend is switched to ReBAC
- **Then** the ReBAC backend does not serve stale RBAC cache entries

**Acceptance Criteria:**
- RBAC and ReBAC use different cache namespaces (`CacheEnum.rbac` vs `CacheEnum.kessel`)
- A backend switch does not result in stale permissions being served
- Each backend only reads from its own cache

---

### IT-MW-AUTH-011: Settings sentinel reported on new customer creation

| Field | Value |
|-------|-------|
| Status | RETIRED — merged into IT-MW-AUTH-005 (identical coverage) |
| Priority | P1 (High) |
| Business Value | When a new organization is created, a settings resource must be reported to Kessel so that settings-level permission checks work |
| Phase | 1 |

**Fixtures:**
- `IamTestCase` base class
- `@override_settings(AUTHORIZATION_BACKEND="rebac")`
- `@patch("koku_rebac.resource_reporter.on_resource_created")`
- Valid `x-rh-identity` header with a new org_id

**Steps:**
- **Given** a request from a user in a brand-new organization
- **When** the middleware creates the customer record
- **Then** `on_resource_created` is called with resource type `"settings"` and the correct org association

**Acceptance Criteria:**
- `on_resource_created("settings", ...)` is called exactly once
- The settings resource ID includes the org_id for unique identification
- The customer record is created in Postgres regardless of the resource reporting outcome

---

## Tier 3 -- Retired Contract Tests (CT)

---

### CT-REL-001: CreateTuples round-trip

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | Validates that the Relations API accepts tuple creation requests and persists them |
| Phase | 1 |

**Prerequisites:**
- Kessel stack running: `podman compose -f dev/kessel/docker-compose.yml up -d`

**Steps:**
- **Given** the Kessel Relations API is running
- **When** a relationship tuple is created via `CreateTuples`
- **Then** the tuple is persisted and can be read back via `ReadTuples`

---

### CT-REL-002: DeleteTuples

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | Validates that relationship tuples can be removed from the Relations API |
| Phase | 1 |

**Steps:**
- **Given** an existing relationship tuple in Kessel
- **When** `DeleteTuples` is called for that tuple
- **Then** the tuple is no longer returned by `ReadTuples`

---

### CT-REL-003: Upsert is idempotent

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Role seeding and binding creation must be safe to retry without errors |
| Phase | 1 |

**Steps:**
- **When** the same tuple is created twice via `CreateTuples`
- **Then** both calls succeed without error

---

### CT-REL-004: Group membership tuples

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Groups are a core Kessel concept; membership tuples must be accepted by the Relations API |
| Phase | 1 |

**Steps:**
- **When** a group membership tuple (`rbac/group#member rbac/principal:user`) is created
- **Then** the tuple is accepted and persisted

---

### CT-REL-005: Role binding with group subject

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Role bindings can target groups, not just individual principals. The Relations API must accept group subjects |
| Phase | 1 |

**Steps:**
- **When** a role binding tuple with a group subject is created
- **Then** the tuple is accepted and persisted

---

### CT-REL-006: Seed roles produces expected tuple count

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; role seeding externalized to `kessel-admin.sh` |
| Priority | P0 (Critical) |
| Business Value | Validates that the `kessel_seed_roles` command produces the correct number of relation tuples for the standard roles |
| Phase | 1 |

**Steps:**
- **When** tuples for all 5 standard roles are written to Kessel
- **Then** the expected number of tuples exists in SpiceDB

---

### CT-REL-007: Schema rejects invalid relation

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Invalid relation names must be rejected to prevent silent configuration errors |
| Phase | 1 |

**Steps:**
- **When** a tuple with a non-existent relation name is created
- **Then** the Relations API returns a gRPC error

---

### CT-REL-008: Multiple members in a single group

| Field | Value |
|-------|-------|
| Status | RETIRED — Koku no longer uses Relations API directly; externalized to `kessel-admin.sh` |
| Priority | P1 (High) |
| Business Value | Groups must support multiple members. This validates fan-out at the Kessel level |
| Phase | 1 |

**Steps:**
- **When** three users are added as members of the same group
- **Then** all three membership tuples are persisted

---

### CT-LOOKUP-001: Authorized user sees the workspace

| Field | Value |
|-------|-------|
| Status | RETIRED — LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| Priority | P0 (Critical) |
| Business Value | Core authorization flow: `LookupResources` must return resources for authorized users |
| Phase | 1 |

**Prerequisites:**
- SpiceDB seeded with test schema, role bindings, and resource data

**Steps:**
- **Given** a user with a role binding granting access to a workspace
- **When** `LookupResources` is called for that user and permission
- **Then** the workspace resource ID is returned

---

### CT-LOOKUP-002: Unauthorized user sees nothing

| Field | Value |
|-------|-------|
| Status | RETIRED — LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| Priority | P0 (Critical) |
| Business Value | Users without role bindings must not see any resources |
| Phase | 1 |

**Steps:**
- **Given** a user with no role bindings
- **When** `LookupResources` is called for that user
- **Then** no resource IDs are returned

---

### CT-LOOKUP-003: Wrong permission returns nothing

| Field | Value |
|-------|-------|
| Status | RETIRED — LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| Priority | P1 (High) |
| Business Value | A user with `read` permission must not be returned for `write` lookups |
| Phase | 1 |

**Steps:**
- **Given** a user with a `read` role binding
- **When** `LookupResources` is called with a `write` permission
- **Then** no resource IDs are returned

---

### CT-LOOKUP-004: Group-based access resolves transitively

| Field | Value |
|-------|-------|
| Status | RETIRED — LookupResources replaced by Inventory API v1beta2 Check/StreamedListObjects |
| Priority | P0 (Critical) |
| Business Value | Group membership must resolve transitively: a user in a group that has a role binding must see resources |
| Phase | 1 |

**Steps:**
- **Given** a user is a member of a group, and the group has a role binding
- **When** `LookupResources` is called for that user
- **Then** the resource IDs from the group's binding are returned

---
