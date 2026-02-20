# Kessel/ReBAC Implementation Guide - OCP Provider

**Parent Document**: [kessel-ocp-integration.md](./kessel-ocp-integration.md)  
**Date**: 2026-01-30  
**Purpose**: Detailed implementation code and examples

---

## Table of Contents

- [Phase 2: ZED Schema Definitions](#phase-2-zed-schema-definitions)
- [Resource Reporter](#resource-reporter)
- [Authorization Service](#authorization-service)
- [Permission Classes](#permission-classes)
- [Sources API Integration](#sources-api-integration)
- [Testing Examples](#testing-examples)
- [Configuration](#configuration)
- [Kessel SDK Usage](#kessel-sdk-usage)

---

## Phase 2: ZED Schema Definitions

### Resource Type Definitions to Submit

**File**: Submit to `github.com/RedHatInsights/rbac-config` - `configs/prod/schemas/schema.zed`

**IMPORTANT ARCHITECTURE NOTE:**

In Kubernetes/OpenShift:
- **Cluster** is the top-level resource
- **Nodes** are worker machines (physical/VM) in the cluster
- **Namespaces/Projects** are logical groupings of resources
- **Projects do NOT belong to nodes** - they are cluster-level constructs
- Pods in a project can be scheduled across multiple nodes

Therefore:
```
Correct:  Cluster → Node
          Cluster → Project

Wrong:    Cluster → Node → Project  ❌
```

```zed
// 1. OpenShift Cluster
definition cost_management/openshift_cluster {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation owner: rbac/principal | rbac/group#member
    
    // Org-level wildcard OR direct relationship
    permission view = viewer + owner + org->cost_management_openshift_cluster_read
    permission manage = owner + org->cost_management_openshift_cluster_all
}

// 2. OpenShift Node (child of cluster)
definition cost_management/openshift_node {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation cluster: cost_management/openshift_cluster
    
    // Inherit from parent cluster OR org-level permission
    permission view = viewer + cluster->view + org->cost_management_openshift_node_read
}

// 3. OpenShift Project (child of cluster, NOT node)
definition cost_management/openshift_project {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation cluster: cost_management/openshift_cluster
    
    // NOTE: Projects are NOT children of nodes!
    // In Kubernetes/OpenShift:
    // - Projects/namespaces are logical groupings at the cluster level
    // - Pods in a project can run on multiple nodes
    // - Many-to-many relationship through pod scheduling
    
    // Inherit from parent cluster OR org-level permission
    permission view = viewer + cluster->view + org->cost_management_openshift_project_read
}
```

---

## Resource Reporter

**Sync Strategy**: Pipeline-driven sync is the recommended approach (see [HLD: Node and Namespace Discovery](./kessel-ocp-integration.md#node-and-namespace-discovery)). Resources are synced to Kessel during data ingestion, tracked via the `kessel_synced_resources` table for idempotency and retry.

**Scope**: Phase 1 targets **new installations only**. Sync/migration from pre-existing Koku deployments will be addressed in a future release.

### Kessel Resource Reporter

**File**: `koku/kessel/resource_reporter.py`

```python
"""Resource reporter for Kessel integration."""
import logging

from api.common import log_json
from django.conf import settings
from kessel_sdk import KesselClient
from kessel_sdk.exceptions import KesselAPIError

LOG = logging.getLogger(__name__)


class KesselResourceReporter:
    """Reports Koku resources to Kessel for authorization."""
    
    def __init__(self, kessel_client=None):
        """
        Initialize the resource reporter.
        
        Args:
            kessel_client: Optional KesselClient instance. If not provided,
                          creates a new client using settings.
        """
        self.client = kessel_client or KesselClient(
            endpoint=settings.KESSEL_CONFIG["endpoint"],
            credentials={"token": settings.KESSEL_CONFIG["token"]},
            timeout=settings.KESSEL_CONFIG["timeout"],
        )
        self.enabled = settings.ONPREM
    
    def report_ocp_cluster(self, cluster_id: str, org_id: str, 
                          tenant_id: str, creator_principal: str) -> bool:
        """
        Report OCP cluster to Kessel.
        
        Creates:
        1. Cluster resource linked to tenant
        2. Owner relationship for creator
        
        Args:
            cluster_id: OpenShift cluster identifier
            org_id: Organization ID for logging
            tenant_id: Tenant/schema identifier
            creator_principal: Username of user creating the provider
        
        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            LOG.debug("Kessel integration disabled, skipping cluster report")
            return True
        
        try:
            self.client.create_relation(
                subject=f"cost_management/openshift_cluster:{cluster_id}",
                relation="org",
                object=f"rbac/tenant:{tenant_id}",
            )
            self.client.create_relation(
                subject=f"rbac/principal:{creator_principal}",
                relation="owner",
                object=f"cost_management/openshift_cluster:{cluster_id}",
            )
            
            LOG.info(log_json(msg="Reported OCP cluster to Kessel",
                              cluster_id=cluster_id, org_id=org_id,
                              tenant_id=tenant_id, creator=creator_principal))
            return True
            
        except KesselAPIError as e:
            LOG.error(log_json(msg="Failed to report cluster to Kessel",
                               cluster_id=cluster_id, org_id=org_id, error=str(e)))
            return False
        except Exception:
            LOG.exception(log_json(msg="Unexpected error reporting cluster to Kessel",
                                   cluster_id=cluster_id, org_id=org_id))
            return False
    
    def report_ocp_node(self, node_id: str, cluster_id: str, 
                       org_id: str, tenant_id: str) -> bool:
        """
        Report OCP node to Kessel with cluster relationship.
        
        Args:
            node_id: Node identifier
            cluster_id: Parent cluster identifier
            org_id: Organization ID for logging
            tenant_id: Tenant/schema identifier
        
        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return True
        
        try:
            self.client.create_relation(
                subject=f"cost_management/openshift_node:{node_id}",
                relation="org",
                object=f"rbac/tenant:{tenant_id}",
            )
            self.client.create_relation(
                subject=f"cost_management/openshift_node:{node_id}",
                relation="cluster",
                object=f"cost_management/openshift_cluster:{cluster_id}",
            )
            
            LOG.info(log_json(msg="Reported OCP node to Kessel",
                              node_id=node_id, cluster_id=cluster_id, org_id=org_id))
            return True
            
        except KesselAPIError as e:
            LOG.error(log_json(msg="Failed to report node to Kessel",
                               node_id=node_id, cluster_id=cluster_id, error=str(e)))
            return False
    
    def report_ocp_project(self, project_id: str, cluster_id: str, 
                          org_id: str, tenant_id: str) -> bool:
        """
        Report OCP project to Kessel with cluster relationship.
        
        NOTE: Projects belong to clusters, NOT nodes. In Kubernetes/OpenShift,
        namespaces/projects are logical groupings at the cluster level, and their
        pods can be scheduled across multiple nodes.
        
        Args:
            project_id: Project/namespace identifier
            cluster_id: Parent cluster identifier (NOT node!)
            org_id: Organization ID for logging
            tenant_id: Tenant/schema identifier
        
        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return True
        
        try:
            self.client.create_relation(
                subject=f"cost_management/openshift_project:{project_id}",
                relation="org",
                object=f"rbac/tenant:{tenant_id}",
            )
            self.client.create_relation(
                subject=f"cost_management/openshift_project:{project_id}",
                relation="cluster",
                object=f"cost_management/openshift_cluster:{cluster_id}",
            )
            
            LOG.info(log_json(msg="Reported OCP project to Kessel",
                              project_id=project_id, cluster_id=cluster_id, org_id=org_id))
            return True
            
        except KesselAPIError as e:
            LOG.error(log_json(msg="Failed to report project to Kessel",
                               project_id=project_id, cluster_id=cluster_id, error=str(e)))
            return False
    
    def remove_ocp_cluster(self, cluster_id: str) -> bool:
        """
        Remove OCP cluster and all related resources from Kessel.
        
        Kessel will cascade delete all relationships (nodes, namespaces).
        
        Args:
            cluster_id: OpenShift cluster identifier
        
        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return True
        
        try:
            self.client.delete_resource(
                resource=f"cost_management/openshift_cluster:{cluster_id}"
            )
            
            LOG.info(log_json(msg="Removed OCP cluster from Kessel",
                              cluster_id=cluster_id))
            return True
            
        except KesselAPIError as e:
            LOG.error(log_json(msg="Failed to remove cluster from Kessel",
                               cluster_id=cluster_id, error=str(e)))
            return False
```

---

## Authorization Service

### Authorization Backend Abstraction

**File**: `koku/kessel/authorization_service.py`

```python
"""Authorization service for Kessel and RBAC backends."""
import logging
from abc import ABC, abstractmethod

from api.common import log_json
from django.conf import settings
from kessel_sdk import KesselClient
from kessel_sdk.exceptions import KesselAPIError

LOG = logging.getLogger(__name__)


class AuthorizationBackend(ABC):
    """Abstract base class for authorization backends."""
    
    @abstractmethod
    def has_permission(self, user, resource_type: str, 
                      verb: str, resource_id: str = None) -> bool:
        """
        Check if user has permission on resource.
        
        Args:
            user: Django user object with access attribute
            resource_type: RBAC resource type (e.g., 'openshift.cluster')
            verb: Permission verb ('read', 'write', '*')
            resource_id: Optional specific resource ID
        
        Returns:
            True if user has permission, False otherwise
        """
        pass


class RBACAuthorizationBackend(AuthorizationBackend):
    """Current RBAC system using OpenShift RBAC API."""
    
    def has_permission(self, user, resource_type, verb, resource_id=None):
        """Check permission using existing RBAC logic."""
        # Get user's access from RBAC API (attached to user object by middleware)
        user_access = user.access.get(resource_type, {}).get(verb, [])
        
        # Check wildcard permission
        if "*" in user_access:
            return True
        
        # Check specific resource permission
        if resource_id and resource_id in user_access:
            return True
        
        return False


class KesselAuthorizationBackend(AuthorizationBackend):
    """Kessel ReBAC authorization system."""
    
    def __init__(self):
        """Initialize Kessel client."""
        self.client = KesselClient(
            endpoint=settings.KESSEL_CONFIG["endpoint"],
            credentials={"token": settings.KESSEL_CONFIG["token"]},
            timeout=settings.KESSEL_CONFIG["timeout"],
        )
        self.cache_enabled = settings.KESSEL_CONFIG.get("cache_enabled", True)
        self.cache_ttl = settings.KESSEL_CONFIG.get("cache_ttl", 30)
    
    def has_permission(self, user, resource_type, verb, resource_id=None):
        """
        Check permission using Kessel Relations API.
        
        Phase 1: Checks org-level wildcard permissions
        Phase 2: Checks resource-specific permissions
        """
        try:
            # Map RBAC resource type to Kessel permission
            permission = self._map_permission(resource_type, verb)
            if not permission:
                LOG.warning(log_json(msg="No Kessel permission mapping",
                                     resource_type=resource_type, verb=verb))
                return False
            
            if resource_id:
                # Phase 2: Check specific resource permission
                kessel_resource = self._map_resource(resource_type, resource_id)
                return self.client.check(
                    subject=f"principal:{user.username}",
                    permission="view",  # or 'manage' for write operations
                    object=kessel_resource
                )
            else:
                # Phase 1: Check org-level wildcard permission
                return self.client.check(
                    subject=f"principal:{user.username}",
                    permission=permission,
                    object=f"tenant:{user.customer.schema_name}"
                )
                
        except KesselAPIError as e:
            LOG.error(log_json(msg="Kessel permission check failed",
                               user=user.username, resource_type=resource_type,
                               verb=verb, resource_id=resource_id, error=str(e)))
            # Fail closed: deny access on Kessel error
            return False
        except Exception:
            LOG.exception(log_json(msg="Unexpected error during Kessel permission check",
                                   user=user.username, resource_type=resource_type))
            return False
    
    def _map_permission(self, resource_type: str, verb: str) -> str:
        """
        Map RBAC resource type and verb to Kessel permission name.
        
        Args:
            resource_type: RBAC resource type (e.g., 'openshift.cluster')
            verb: Permission verb ('read', 'write', '*')
        
        Returns:
            Kessel permission name or None if no mapping exists
        """
        mapping = {
            ("openshift.cluster", "read"): "cost_management_openshift_cluster_read",
            ("openshift.cluster", "*"): "cost_management_openshift_cluster_all",
            ("openshift.node", "read"): "cost_management_openshift_node_read",
            ("openshift.node", "*"): "cost_management_openshift_node_all",
            ("openshift.project", "read"): "cost_management_openshift_project_read",
            ("openshift.project", "*"): "cost_management_openshift_project_all",
        }
        return mapping.get((resource_type, verb))
    
    def _map_resource(self, resource_type: str, resource_id: str) -> str:
        """
        Map RBAC resource type and ID to Kessel resource identifier.
        
        Args:
            resource_type: RBAC resource type
            resource_id: Resource identifier
        
        Returns:
            Kessel resource identifier
        """
        mapping = {
            "openshift.cluster": f"cost_management/openshift_cluster:{resource_id}",
            "openshift.node": f"cost_management/openshift_node:{resource_id}",
            "openshift.project": f"cost_management/openshift_project:{resource_id}",
        }
        return mapping.get(resource_type)


# Singleton instance
_authorization_service = None


def get_authorization_service() -> AuthorizationBackend:
    """
    Get the configured authorization backend.
    
    Returns singleton instance based on ONPREM setting.
    """
    global _authorization_service
    
    if _authorization_service is None:
        if settings.ONPREM:
            LOG.info(log_json(msg="Using Kessel authorization backend"))
            _authorization_service = KesselAuthorizationBackend()
        else:
            LOG.info(log_json(msg="Using RBAC authorization backend"))
            _authorization_service = RBACAuthorizationBackend()
    
    return _authorization_service
```

---

## Permission Classes

### OpenShift Permission Classes with Kessel Support

**File**: `koku/api/common/permissions/openshift_access.py`

**Note**: The existing file only contains `has_permission()` on each class. The `has_object_permission()` methods shown below are **NEW additions for Phase 2** (resource-specific permissions). Phase 1 only modifies `has_permission()` to use the authorization service abstraction.

```python
"""OpenShift access permission classes with Kessel support."""
from rest_framework.permissions import BasePermission
from kessel.authorization_service import get_authorization_service


class OpenShiftAccessPermission(BasePermission):
    """Permission class for openshift.cluster access."""
    
    resource_type = "openshift.cluster"
    
    def has_permission(self, request, view):
        """
        Check if user has cluster access (wildcard).
        
        Called before view execution to check general cluster access.
        Existing method — modified to use authorization service.
        """
        auth_service = get_authorization_service()
        
        # Check wildcard access
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read"
        )
    
    # NEW — Phase 2 only (does not exist in current codebase)
    def has_object_permission(self, request, view, obj):
        """
        Check if user has access to specific cluster.
        
        Called when accessing a specific cluster object.
        NEW method added in Phase 2 for resource-specific permissions.
        """
        auth_service = get_authorization_service()
        
        # Extract cluster ID from object
        cluster_id = getattr(obj, "cluster_id", None)
        if not cluster_id:
            # If no cluster_id, fall back to wildcard check
            return self.has_permission(request, view)
        
        # Check specific cluster access
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read",
            resource_id=cluster_id
        )


class OpenShiftNodePermission(BasePermission):
    """Permission class for openshift.node access."""
    
    resource_type = "openshift.node"
    
    def has_permission(self, request, view):
        """Check if user has node access (wildcard). Existing — modified."""
        auth_service = get_authorization_service()
        
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read"
        )
    
    # NEW — Phase 2 only
    def has_object_permission(self, request, view, obj):
        """Check if user has access to specific node. NEW in Phase 2."""
        auth_service = get_authorization_service()
        
        node_id = getattr(obj, "node_id", None)
        if not node_id:
            return self.has_permission(request, view)
        
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read",
            resource_id=node_id
        )


class OpenShiftProjectPermission(BasePermission):
    """Permission class for openshift.project access."""
    
    resource_type = "openshift.project"
    
    def has_permission(self, request, view):
        """Check if user has project access (wildcard). Existing — modified."""
        auth_service = get_authorization_service()
        
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read"
        )
    
    # NEW — Phase 2 only
    def has_object_permission(self, request, view, obj):
        """Check if user has access to specific project. NEW in Phase 2."""
        auth_service = get_authorization_service()
        
        project_id = getattr(obj, "namespace", None)  # OCP uses "namespace"
        if not project_id:
            return self.has_permission(request, view)
        
        return auth_service.has_permission(
            user=request.user,
            resource_type=self.resource_type,
            verb="read",
            resource_id=project_id
        )
```

---

## Sources API Integration

### ProviderBuilder Integration

**File**: `koku/api/provider/provider_builder.py`

**Add imports**:
```python
from api.common import log_json
from django.conf import settings
from kessel.resource_reporter import KesselResourceReporter
```

**Modify `create_provider_from_source()` method**:
```python
def create_provider_from_source(self, source):
    """
    Create provider from source (existing method with Kessel integration).
    
    This method is called by Sources API when a new provider is created.
    
    Args:
        source: Source model instance
    """
    # ... existing validation and setup code ...
    
    provider = None
    try:
        # Existing provider creation logic
        provider = self._create_provider(...)
        
        # NEW: Report to Kessel if OCP provider and on-prem deployment
        if provider.type == Provider.PROVIDER_OCP:
            self._report_ocp_cluster_to_kessel(provider, customer)
        
        # ... existing post-creation logic ...
        
        return provider
        
    except Exception as error:
        # ... existing error handling ...
        raise
```

**Add new helper method**:
```python
def _report_ocp_cluster_to_kessel(self, provider, customer):
    """
    Report OCP cluster to Kessel resource registry.
    
    Args:
        provider: Provider model instance
        customer: Customer model instance
    """
    if not settings.ONPREM:
        return
    
    try:
        reporter = KesselResourceReporter()
        cluster_id = provider.authentication.credentials.get("cluster_id")
        creator = self.request_context.get("user", {}).get("username")
        
        if not cluster_id:
            LOG.warning(
                log_json(msg="No cluster_id found for OCP provider, skipping Kessel report",
                         provider_uuid=str(provider.uuid))
            )
            return
        
        success = reporter.report_ocp_cluster(
            cluster_id=cluster_id,
            org_id=customer.org_id,
            tenant_id=customer.schema_name,
            creator_principal=creator,
        )
        
        if not success:
            LOG.warning(
                log_json(msg="Failed to report OCP cluster to Kessel",
                         cluster_id=cluster_id, org_id=customer.org_id,
                         provider_uuid=str(provider.uuid))
            )
    except Exception as e:
        LOG.error(
            log_json(msg="Exception reporting OCP cluster to Kessel",
                     provider_uuid=str(provider.uuid), error=str(e)),
            exc_info=True,
        )
```

**Modify `destroy_provider()` method**:
```python
def destroy_provider(self, provider_uuid, retry_count=None):
    """
    Remove provider (existing method with Kessel cleanup).
    
    Deletion order: Koku/Postgres first, then Kessel.
    This ensures the core deletion succeeds before attempting
    external cleanup. Kessel failures are logged but do not
    revert the Koku deletion.
    
    Args:
        provider_uuid: UUID of provider to delete
        retry_count: Optional retry count
    """
    provider = Provider.objects.get(uuid=provider_uuid)
    
    # ... existing Postgres deletion logic (runs first) ...
    
    # AFTER successful Postgres deletion, clean up Kessel
    if provider.type == Provider.PROVIDER_OCP:
        self._remove_ocp_cluster_from_kessel(provider)
```

**Add new helper method**:
```python
def _remove_ocp_cluster_from_kessel(self, provider):
    """
    Remove OCP cluster from Kessel resource registry.
    
    Called AFTER successful Postgres deletion. Kessel cleanup
    failure is logged but does not revert the Koku deletion.
    
    Args:
        provider: Provider model instance
    """
    if not settings.ONPREM:
        return
    
    try:
        reporter = KesselResourceReporter()
        cluster_id = provider.authentication.credentials.get("cluster_id")
        
        if not cluster_id:
            LOG.warning(
                log_json(msg="No cluster_id found for OCP provider, skipping Kessel cleanup",
                         provider_uuid=str(provider.uuid))
            )
            return
        
        reporter.remove_ocp_cluster(cluster_id=cluster_id)
        
    except Exception as e:
        LOG.error(
            log_json(msg="Failed to remove OCP cluster from Kessel",
                     provider_uuid=str(provider.uuid), error=str(e)),
            exc_info=True
        )
        # Koku deletion already succeeded; log but don't revert
```

---

## Testing Examples

### Unit Tests for Authorization Service

**File**: `koku/kessel/test/test_authorization_service.py`

```python
"""Tests for Kessel authorization service."""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from kessel.authorization_service import (
    KesselAuthorizationBackend,
    RBACAuthorizationBackend,
    get_authorization_service
)


class TestKesselAuthorizationBackend(TestCase):
    """Tests for Kessel authorization backend."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.user = MagicMock()
        self.user.username = "alice"
        self.user.customer.schema_name = "org123"
    
    @patch("kessel.authorization_service.KesselClient")
    def test_wildcard_cluster_access(self, mock_client_class):
        """Test org-level wildcard cluster permission."""
        mock_client = MagicMock()
        mock_client.check.return_value = True
        mock_client_class.return_value = mock_client
        
        backend = KesselAuthorizationBackend()
        
        result = backend.has_permission(
            user=self.user,
            resource_type="openshift.cluster",
            verb="read",
        )
        
        self.assertTrue(result)
        mock_client.check.assert_called_once_with(
            subject="principal:alice",
            permission="cost_management_openshift_cluster_read",
            object="tenant:org123",
        )
    
    @patch("kessel.authorization_service.KesselClient")
    def test_specific_cluster_access(self, mock_client_class):
        """Test specific cluster resource permission (Phase 2)."""
        mock_client = MagicMock()
        mock_client.check.return_value = True
        mock_client_class.return_value = mock_client
        
        backend = KesselAuthorizationBackend()
        
        result = backend.has_permission(
            user=self.user,
            resource_type="openshift.cluster",
            verb="read",
            resource_id="cluster-abc-123",
        )
        
        self.assertTrue(result)
        mock_client.check.assert_called_once_with(
            subject="principal:alice",
            permission="view",
            object="cost_management/openshift_cluster:cluster-abc-123",
        )
    
    @patch("kessel.authorization_service.KesselClient")
    def test_no_cluster_access(self, mock_client_class):
        """Test denied cluster access."""
        mock_client = MagicMock()
        mock_client.check.return_value = False
        mock_client_class.return_value = mock_client
        
        backend = KesselAuthorizationBackend()
        
        result = backend.has_permission(
            user=self.user,
            resource_type="openshift.cluster",
            verb="read"
        )
        
        self.assertFalse(result)


class TestRBACAuthorizationBackend(TestCase):
    """Tests for RBAC authorization backend."""
    
    def test_wildcard_access(self):
        """Test wildcard access check."""
        user = MagicMock()
        user.access = {
            "openshift.cluster": {"read": ["*"]}
        }
        
        backend = RBACAuthorizationBackend()
        result = backend.has_permission(user, "openshift.cluster", "read")
        
        self.assertTrue(result)
    
    def test_specific_resource_access(self):
        """Test specific resource ID access."""
        user = MagicMock()
        user.access = {
            "openshift.cluster": {"read": ["cluster-1", "cluster-2"]}
        }
        
        backend = RBACAuthorizationBackend()
        
        # User has access to cluster-1
        result = backend.has_permission(
            user, "openshift.cluster", "read", "cluster-1"
        )
        self.assertTrue(result)
        
        # User doesn't have access to cluster-3
        result = backend.has_permission(
            user, "openshift.cluster", "read", "cluster-3"
        )
        self.assertFalse(result)
```

### Integration Tests for Provider Creation

**File**: `koku/api/provider/test/test_provider_builder_kessel.py`

```python
"""Integration tests for ProviderBuilder with Kessel."""
from unittest.mock import patch, MagicMock
from django.test import override_settings

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider


class TestProviderBuilderKesselIntegration(IamTestCase):
    """Tests for ProviderBuilder Kessel integration."""
    
    @override_settings(ONPREM=True)
    @patch("kessel.resource_reporter.KesselResourceReporter")
    def test_create_ocp_provider_reports_to_kessel(self, mock_reporter_class):
        """Test OCP provider creation reports cluster to Kessel."""
        mock_reporter = MagicMock()
        mock_reporter.report_ocp_cluster.return_value = True
        mock_reporter_class.return_value = mock_reporter
        
        # Create provider (details depend on test fixtures from IamTestCase)
        builder = ProviderBuilder(...)
        provider = builder.create_provider_from_source(...)
        
        self.assertEqual(provider.type, Provider.PROVIDER_OCP)
        mock_reporter.report_ocp_cluster.assert_called_once_with(
            cluster_id=provider.authentication.credentials["cluster_id"],
            org_id=...,
            tenant_id=...,
            creator_principal=...,
        )
    
    @override_settings(ONPREM=True)
    @patch("kessel.resource_reporter.KesselResourceReporter")
    def test_kessel_failure_does_not_block_provider_creation(self, mock_reporter_class):
        """Test provider creation succeeds even if Kessel fails."""
        mock_reporter = MagicMock()
        mock_reporter.report_ocp_cluster.return_value = False
        mock_reporter_class.return_value = mock_reporter
        
        builder = ProviderBuilder(...)
        provider = builder.create_provider_from_source(...)
        
        self.assertIsNotNone(provider)
        self.assertEqual(provider.type, Provider.PROVIDER_OCP)
```

---

## Configuration

### Environment Variables

```bash
# Enable Kessel authorization backend
ONPREM=true

# Kessel connection details
KESSEL_ENDPOINT=kessel.example.com:8443
KESSEL_TOKEN=<auth-token>

# Optional: Kessel connection timeout (seconds)
KESSEL_TIMEOUT=10

# Optional: Enable Kessel permission caching
KESSEL_CACHE_ENABLED=true
KESSEL_CACHE_TTL=30
```

### Django Settings

**File**: `koku/koku/settings.py`

```python
# ENVIRONMENT is already defined in settings.py as:
# ENVIRONMENT = environ.Env()

# Enable Kessel for on-premise deployments
ONPREM = ENVIRONMENT.bool("ONPREM", default=False)

# Kessel configuration
KESSEL_CONFIG = {
    "endpoint": ENVIRONMENT.get_value("KESSEL_ENDPOINT", default=""),
    "token": ENVIRONMENT.get_value("KESSEL_TOKEN", default=""),
    "timeout": ENVIRONMENT.int("KESSEL_TIMEOUT", default=10),
    "cache_enabled": ENVIRONMENT.bool("KESSEL_CACHE_ENABLED", default=True),
    "cache_ttl": ENVIRONMENT.int("KESSEL_CACHE_TTL", default=30),
}

# Validate Kessel config when enabled
if ONPREM:
    if not KESSEL_CONFIG["endpoint"]:
        raise ValueError("KESSEL_ENDPOINT must be set when ONPREM is True")
    if not KESSEL_CONFIG["token"]:
        raise ValueError("KESSEL_TOKEN must be set when ONPREM is True")
```

---

## Kessel SDK Usage

### Basic Operations

```python
from kessel_sdk import KesselClient

# Initialize client
client = KesselClient(
    endpoint="kessel.example.com:8443",
    credentials={"token": "your-auth-token"}
)

# Check permission (wildcard - org level)
allowed = client.check(
    subject="principal:alice",
    permission="cost_management_openshift_cluster_read",
    object="tenant:org123"
)

# Check permission (specific resource - Phase 2)
allowed = client.check(
    subject="principal:alice",
    permission="view",
    object="cost_management/openshift_cluster:cluster-abc-123"
)

# Create resource relationship
client.create_relation(
    subject="cost_management/openshift_cluster:cluster-abc-123",
    relation="org",
    object="rbac/tenant:org123"
)

# Create ownership relationship
client.create_relation(
    subject="rbac/principal:alice",
    relation="owner",
    object="cost_management/openshift_cluster:cluster-abc-123"
)

# Create hierarchical relationship (node → cluster)
client.create_relation(
    subject="cost_management/openshift_node:node-123",
    relation="cluster",
    object="cost_management/openshift_cluster:cluster-abc-123"
)

# Delete resource (cascades relationships)
client.delete_resource(
    resource="cost_management/openshift_cluster:cluster-abc-123"
)
```

### Error Handling

```python
from kessel_sdk.exceptions import KesselAPIError, KesselConnectionError

try:
    result = client.check(
        subject="principal:alice",
        permission="cost_management_openshift_cluster_read",
        object="tenant:org123"
    )
except KesselConnectionError as e:
    # Handle connection failures
    LOG.error(f"Cannot connect to Kessel: {e}")
    # Fail closed or use cached result
    result = False
except KesselAPIError as e:
    # Handle API errors (400, 500, etc.)
    LOG.error(f"Kessel API error: {e}")
    result = False
```

---

**Document Version**: 1.1  
**Last Updated**: 2026-02-13  
**Parent Document**: [kessel-ocp-integration.md](./kessel-ocp-integration.md)
