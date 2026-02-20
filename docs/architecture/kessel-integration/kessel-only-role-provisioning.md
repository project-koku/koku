# Kessel-Only Deployment: Role Provisioning Strategy

**Date**: 2026-02-13  
**Version**: 1.1  
**Deployment Model**: Kessel ONLY (no RBAC Service)  
**Critical Finding**: Role instances must be created in Kessel

---

## Executive Summary

**On-premise architecture**: Kessel ONLY (no RBAC Service)

**What this means**:
- ✅ Permission **definitions** exist in schema.zed (type system)
- ❌ Role **instances** (e.g., "Cost Administrator") do NOT automatically exist
- ⚠️ Operators must create role instances in Kessel
- ⚠️ `roles.json` is a **reference**, not automatically loaded

**Recommendation**: Provide role seeding tool/script for on-premise operators.

---

## Schema vs Data Clarification

### What's IN schema.zed (Deployed to Kessel)

**Permission TYPE definitions** on `rbac/role`:

```zed
definition rbac/role {
    // This defines what permissions a role CAN have
    permission cost_management_openshift_cluster_read = t_cost_management_openshift_cluster_read
    relation t_cost_management_openshift_cluster_read: rbac/principal:*
    
    permission cost_management_cost_model_write = t_cost_management_cost_model_write
    relation t_cost_management_cost_model_write: rbac/principal:*
    // ... 12 total permissions
}
```

**This is the TYPE SYSTEM** - like a class definition in programming.

### What's NOT IN schema.zed (NOT Automatically in Kessel)

**Role INSTANCES** like:
- ❌ `rbac/role:cost-administrator`
- ❌ `rbac/role:cost-openshift-viewer`
- ❌ `rbac/role:cost-price-list-administrator`

**These are DATA/INSTANCES** - like objects in programming.

### Where Role Instances Come From

**In SaaS**:
```
roles.json → RBAC Service DB → Available for role bindings
```

**In On-Premise (Kessel-only)**:
```
roles.json → ??? → Must be created in Kessel manually
```

**Gap**: No automatic role instance provisioning!

---

## What Operators Must Do (Current State)

### Manual Role Instance Creation

**For each role** in `roles.json`, operators must:

1. **Create role resource in Kessel**
```bash
# This creates the role instance
# Note: Kessel doesn't have a "create resource" API per se
# Roles are implicitly created when relationships reference them
```

2. **Create role permissions**

For "Cost OpenShift Viewer" role:
```python
# Grant the role the required permission
kessel.CreateRelation(
    subject="rbac/role:cost-openshift-viewer",
    relation="t_cost_management_openshift_cluster_read",  # Permission from schema
    object="rbac/principal:*"  # Available to all principals who have this role
)
```

3. **Assign users to role**
```python
# Create role binding
kessel.CreateRelation(
    subject="rbac/principal:alice",
    relation="member",
    object="rbac/role_binding:alice-binding"
)

# Link binding to role
kessel.CreateRelation(
    subject="rbac/role_binding:alice-binding",
    relation="grants",
    object="rbac/role:cost-openshift-viewer"  # Role we just created
)

# Link binding to tenant
kessel.CreateRelation(
    subject="rbac/role_binding:alice-binding",
    relation="t_binding",
    object="rbac/tenant:org-123"
)
```

**Problem**: This is complex, error-prone, and requires deep Kessel knowledge!

---

## Proposed Solution: Role Seeding Tool

### Option 1: Koku Management Command (Recommended)

**New management command**: `python manage.py kessel_seed_roles`

**Purpose**: Create standard Cost Management roles in Kessel based on `rbac-config/roles/cost-management.json`

**Implementation**:

**File**: `koku/kessel/management/commands/kessel_seed_roles.py`

```python
"""Management command to seed Cost Management roles into Kessel."""
from django.core.management.base import BaseCommand
from django.conf import settings
from kessel_sdk import KesselClient
import json
import requests

ROLES_JSON_URL = "https://raw.githubusercontent.com/RedHatInsights/rbac-config/master/configs/prod/roles/cost-management.json"

# Mapping from RBAC permission format to Kessel relation names
PERMISSION_MAPPING = {
    "cost-management:*:*": [
        "t_cost_management_aws_account_all",
        "t_cost_management_aws_account_read",
        "t_cost_management_azure_subscription_guid_all",
        "t_cost_management_azure_subscription_guid_read",
        "t_cost_management_gcp_account_all",
        "t_cost_management_gcp_account_read",
        "t_cost_management_gcp_project_all",
        "t_cost_management_gcp_project_read",
        "t_cost_management_openshift_cluster_all",
        "t_cost_management_openshift_cluster_read",
        "t_cost_management_openshift_node_all",
        "t_cost_management_openshift_node_read",
        "t_cost_management_openshift_project_all",
        "t_cost_management_openshift_project_read",
        "t_cost_management_cost_model_all",
        "t_cost_management_cost_model_read",
        "t_cost_management_cost_model_write",
        "t_cost_management_settings_all",
        "t_cost_management_settings_read",
        "t_cost_management_settings_write",
    ],
    "cost-management:openshift.cluster:*": [
        "t_cost_management_openshift_cluster_all",
        "t_cost_management_openshift_cluster_read",
    ],
    "cost-management:cost_model:read": [
        "t_cost_management_cost_model_read",
    ],
    "cost-management:cost_model:write": [
        "t_cost_management_cost_model_write",
    ],
    # ... etc
}

class Command(BaseCommand):
    help = "Seed Cost Management roles into Kessel from rbac-config"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--roles-file',
            type=str,
            help='Path to local roles JSON file (default: fetch from GitHub)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating'
        )
    
    def handle(self, *args, **options):
        if not settings.ONPREM:
            self.stdout.write(self.style.WARNING(
                "ONPREM is False - roles seeding is only for on-premise"
            ))
            return
        
        # Initialize Kessel client
        client = KesselClient(
            endpoint=settings.KESSEL_CONFIG['endpoint'],
            credentials={'token': settings.KESSEL_CONFIG['token']}
        )
        
        # Load roles
        if options['roles_file']:
            with open(options['roles_file']) as f:
                roles_data = json.load(f)
        else:
            self.stdout.write("Fetching roles from rbac-config...")
            response = requests.get(ROLES_JSON_URL)
            roles_data = response.json()
        
        roles = roles_data.get('roles', [])
        self.stdout.write(self.style.SUCCESS(f"Found {len(roles)} roles to seed"))
        
        # Create each role
        for role in roles:
            role_name = role['name']
            role_slug = role_name.lower().replace(' ', '-')
            role_resource = f"rbac/role:{role_slug}"
            
            self.stdout.write(f"\nSeeding role: {role_name}")
            self.stdout.write(f"  Resource: {role_resource}")
            self.stdout.write(f"  Description: {role['description']}")
            
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("  [DRY RUN] Would create role"))
                continue
            
            # Create role permissions based on access
            for access in role.get('access', []):
                permission = access['permission']
                
                # Map RBAC permission to Kessel relations
                kessel_relations = self._map_permission_to_relations(permission)
                
                for relation_name in kessel_relations:
                    try:
                        client.create_relation(
                            subject=role_resource,
                            relation=relation_name,
                            object="rbac/principal:*"
                        )
                        self.stdout.write(f"    ✓ Added permission: {relation_name}")
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"    ✗ Failed to add {relation_name}: {e}")
                        )
        
        self.stdout.write(self.style.SUCCESS("\n✓ Role seeding complete"))
    
    def _map_permission_to_relations(self, permission):
        """Map RBAC permission string to Kessel relation names."""
        return PERMISSION_MAPPING.get(permission, [])
```

**Usage**:
```bash
# Seed all standard roles
python manage.py kessel_seed_roles

# Dry run first
python manage.py kessel_seed_roles --dry-run

# Use local roles file
python manage.py kessel_seed_roles --roles-file /path/to/roles.json
```

### Option 2: Standalone Script (Language-Agnostic)

**File**: `scripts/kessel_seed_roles.sh` or `.py`

**Advantage**: Can be used without Koku running  
**Disadvantage**: Separate from Koku codebase

### Option 3: Documentation Only

**File**: Operator guide with Kessel API calls

**Advantage**: No code needed  
**Disadvantage**: Manual, error-prone, requires Kessel expertise

**Recommendation**: Option 1 (management command)

---

## Updated Understanding

### Correct Statement

**What's in Red Hat schema.zed**:
- ✅ Permission TYPE definitions (12 cost_management permissions)
- ✅ Role TYPE definition (`definition rbac/role`)
- ✅ 3-tier model (principal, role_binding, platform, tenant)

**What's NOT in schema.zed**:
- ❌ Role INSTANCES (Cost Administrator, Cost OpenShift Viewer, etc.)
- ❌ These live in RBAC Service database (SaaS)
- ❌ Must be created manually in Kessel (on-prem)

**What's in roles.json**:
- ✅ Configuration data for RBAC Service (SaaS)
- ✅ Reference documentation for on-prem operators
- ❌ Not automatically loaded into Kessel

### Impact on Phase 1

**Phase 1 operators must**:

1. **Deploy Kessel + schema.zed** ✅ Simple
2. **Create role instances** ⚠️ Complex (need tool/script)
3. **Create role bindings** ⚠️ Complex (manual Kessel API calls)
4. **Assign users to roles** ⚠️ Complex (manual Kessel API calls)

**Without tooling**: Phase 1 is much harder than HLD suggests!

**With tooling** (seeding script): Phase 1 is manageable.

---

## Recommendations for Koku HLD

### 1. Add Critical Architecture Decision

**Section**: "Deployment Architecture"

```markdown
### On-Premise Architecture: Kessel-Only

On-premise deployments will use **Kessel only** (no RBAC Service).

**Implications**:
- Permission definitions exist in schema.zed ✅
- Role instances must be created in Kessel ⚠️
- Role management via Kessel API (no UI) ⚠️

**Solution**: Koku provides role seeding tool to create standard roles.
```

### 2. Update Phase 1 Deployment Steps

**Current** (incomplete):
> "Deploy Kessel with Red Hat platform schema"

**Updated** (complete):
> **Phase 1 Deployment for On-Premise:**
> 
> 1. Deploy Kessel instance
> 2. Deploy Red Hat platform schema to Kessel:
>    ```bash
>    curl -o schema.zed https://raw.githubusercontent.com/RedHatInsights/rbac-config/master/configs/prod/schemas/schema.zed
>    spicedb schema write --schema schema.zed
>    ```
> 3. **Configure Koku**: `ONPREM=true`, `KESSEL_ENDPOINT`, `KESSEL_TOKEN`
> 4. **Seed standard roles** into Kessel:
>    ```bash
>    python manage.py kessel_seed_roles
>    ```
>    This creates role instances based on `rbac-config/roles/cost-management.json`
> 5. Create tenant resources for organization
> 6. Assign users to roles via role bindings

### 3. Add New Component to Implementation

**New Component**: Role Seeding Tool

**Purpose**: Automatically create standard Cost Management role instances in Kessel based on Red Hat's `rbac-config/roles/cost-management.json`.

**Implementation Options**:
1. Django management command (recommended)
2. Standalone Python script
3. Shell script with Kessel API calls

**Why needed**: Kessel-only deployment doesn't have RBAC Service to manage role instances.

### 4. Update "What's Included" (Phase 1)

**Add**:
✅ **Role Seeding Tool**
- Creates 5 standard Cost Management roles in Kessel
- Based on Red Hat's production role definitions
- Idempotent and safe to re-run

### 5. Add to Open Questions

**Q: Should operators use standard roles or create custom roles?**
- **Recommendation**: Use standard roles (via seeding tool)
- **Rationale**: Production-tested, covers common use cases
- **Custom roles**: Only if specific needs not met by standard roles

---

## Detailed Role Seeding Approach

### Standard Roles to Seed

**From**: `github.com/RedHatInsights/rbac-config/configs/prod/roles/cost-management.json`

**5 roles to create**:

#### 1. Cost Administrator
```python
role_id = "rbac/role:cost-administrator"

# Grant ALL permissions
for permission in ALL_COST_MANAGEMENT_PERMISSIONS:
    kessel.CreateRelation(
        subject=role_id,
        relation=permission,  # e.g., "t_cost_management_openshift_cluster_read"
        object="rbac/principal:*"
    )
```

#### 2. Cost OpenShift Viewer
```python
role_id = "rbac/role:cost-openshift-viewer"

# Grant OCP permissions only
kessel.CreateRelation(
    subject=role_id,
    relation="t_cost_management_openshift_cluster_all",
    object="rbac/principal:*"
)
kessel.CreateRelation(
    subject=role_id,
    relation="t_cost_management_openshift_cluster_read",
    object="rbac/principal:*"
)
# Note: Original role uses "openshift.cluster:*" which maps to both _all and _read
```

#### 3-5. Similar for other roles
- Cost Cloud Viewer (AWS, Azure, GCP permissions)
- Cost Price List Administrator (cost_model read + write)
- Cost Price List Viewer (cost_model read only)

### Permission Mapping Logic

**RBAC permission format**: `cost-management:resource_type:verb`

**Kessel relation format**: `t_cost_management_{resource}_{verb}`

**Mapping examples**:

| RBAC Permission | Kessel Relations |
|----------------|------------------|
| `cost-management:*:*` | ALL 20 relations |
| `cost-management:openshift.cluster:*` | `t_cost_management_openshift_cluster_all`<br/>`t_cost_management_openshift_cluster_read` |
| `cost-management:cost_model:read` | `t_cost_management_cost_model_read` |
| `cost-management:cost_model:write` | `t_cost_management_cost_model_write` |

**Challenge**: The `*` verb in RBAC doesn't map 1:1 to Kessel

**Solution in seeding tool**:
```python
def map_permission(rbac_perm):
    """Map RBAC permission to Kessel relations."""
    app, resource, verb = rbac_perm.split(':')
    
    if verb == '*':
        # Grant both _all and _read (or all verbs)
        return [
            f"t_cost_management_{resource.replace('.', '_')}_all",
            f"t_cost_management_{resource.replace('.', '_')}_read",
            # Add _write if applicable
        ]
    else:
        return [f"t_cost_management_{resource.replace('.', '_')}_{verb}"]
```

---

## Alternative: Simplified Role Model

### Instead of Replicating All 5 Roles

**Simpler approach for Phase 1**:

**Create 2 basic roles only**:

1. **OCP Admin** (all OCP permissions)
   ```python
   role_id = "rbac/role:ocp-admin"
   # Grant: openshift.cluster, openshift.node, openshift.project (all verbs)
   ```

2. **OCP Viewer** (read-only OCP permissions)
   ```python
   role_id = "rbac/role:ocp-viewer"
   # Grant: openshift.cluster, openshift.node, openshift.project (read only)
   ```

**Advantages**:
- ✅ Simpler to implement
- ✅ Covers 90% of on-prem use cases
- ✅ OCP-only focus (matches HLD scope)
- ✅ Easier to understand for operators

**Disadvantages**:
- ❌ Not using Red Hat's standard role names
- ❌ Less granular than 5 standard roles

**Recommendation**: Start simple (2 roles), add more if needed.

---

## Impact on HLD Components

### 1. Phase 1 Deployment Complexity

**Previous understanding**: 
> "Just deploy schema, assign users to roles"

**Corrected understanding**:
> "Deploy schema, **create role instances**, then assign users"

**Complexity increase**: Moderate (mitigated by seeding tool)

### 2. New Component Required

**Add to Implementation Details**:

**Component**: Role Seeding Tool
- **Purpose**: Create standard role instances in Kessel
- **Type**: Django management command
- **Input**: Red Hat's `roles.json` (reference)
- **Output**: Role instances in Kessel
- **When**: Run once during initial Kessel setup

### 3. Operator Experience

**Without seeding tool**:
```bash
# Operator must manually create 5 roles with ~50 permission relations
# Complex, error-prone, requires deep Kessel knowledge
```

**With seeding tool**:
```bash
# Operator runs simple command
python manage.py kessel_seed_roles
# ✓ 5 standard roles created
# ✓ All permissions configured
# ✓ Ready for user assignment
```

**Operator experience**: Much better with tooling!

---

## Updated HLD Requirements

### Add to Phase 1 Development Tasks

**Week 1-2: Development**
- [ ] Implement `AuthorizationBackend` abstraction
- [ ] Implement `KesselAuthorizationBackend` with wildcard checks
- [ ] Update permission classes to use authorization service
- [ ] **NEW**: Implement role seeding management command
- [ ] Add configuration for Kessel endpoint
- [ ] Unit tests for authorization service
- [ ] **NEW**: Unit tests for role seeding

### Add to Phase 1 Deployment Guide

**For On-Premise Operators**:

1. Deploy Kessel instance
2. Deploy schema: `spicedb schema write --schema schema.zed`
3. Configure Koku: `ONPREM=true`, `KESSEL_ENDPOINT`, `KESSEL_TOKEN`
4. **Seed roles**: `python manage.py kessel_seed_roles`
5. Create tenant: (manual or via Koku API)
6. Assign users to roles: (manual Kessel API calls or future Koku UI)

---

## Summary: What On-Prem Gets from rbac-config

### ✅ FROM schema.zed (Automatic)

- Permission type definitions (12 permissions)
- Role type definition
- 3-tier model structure
- Group support
- Workspace support

**Deployment**: One command (`spicedb schema write`)

### ⚠️ FROM roles.json (Requires Tooling)

- Role instance definitions (5 standard roles)
- Permission-to-role mappings
- Role descriptions and metadata

**Deployment**: Requires seeding tool/script

### ❌ NOT Available (Must Create)

- Role instances in Kessel (created by seeding tool)
- User principals (created per-deployment)
- Role bindings (user-to-role assignments)
- Tenant resources (organization entities)

---

## Recommendation

### Update Koku HLD to Include

1. **Clarify deployment model**: Kessel-only (no RBAC Service)
2. **Add role seeding component**: Management command or script
3. **Update deployment steps**: Include `kessel_seed_roles` step
4. **Update timeline**: Add 1-2 days for role seeding implementation
5. **Document operator workflow**: Schema → Roles → Users → Bindings

### Priority

**HIGH** - This is critical infrastructure that affects:
- Operator experience
- Deployment complexity
- Phase 1 timeline
- Documentation accuracy

These recommendations have been incorporated into the parent HLD ([kessel-ocp-integration.md](./kessel-ocp-integration.md)).