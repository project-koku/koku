# Koku vs ROS OCP Backend - ReBAC Design Comparison

**Date**: 2026-01-30  
**Updated**: 2026-02-04 (verified upstream repo)  
**Status**: Comparison Analysis  
**Purpose**: Compare ReBAC approaches between Koku and ROS OCP Backend

**Repositories Checked**:
- **Upstream**: https://github.com/RedHatInsights/ros-ocp-backend
- **Fork**: https://github.com/insights-onprem/ros-ocp-backend
- **Status**: Both repositories are identical (no ReBAC work in either)

---

## Executive Summary

**Critical Finding**: ROS OCP Backend (both upstream and fork) **does NOT have a ReBAC design** yet. They are still using the traditional RBAC API with no ReBAC implementation or design documentation.

**Comparison Scope**:
- Koku: **Has complete HLD** for ReBAC integration
- ROS (both repos): **No ReBAC design** - still using RBAC API only

---

## Repository Investigation Results

### Upstream vs Fork Comparison

**Checked Repositories**:
1. **Upstream**: `RedHatInsights/ros-ocp-backend` (public, primary development)
2. **Fork**: `insights-onprem/ros-ocp-backend` (fork for on-premise work)

**Findings**:

| Aspect | Upstream | Fork | Verdict |
|--------|----------|------|---------|
| **ReBAC Code** | ❌ None | ❌ None | Identical |
| **RBAC Implementation** | ✅ `internal/api/middleware/rbac.go` | ✅ Same file | Identical |
| **ReBAC PRs** | ❌ None (checked 100 PRs) | ❌ None (checked 50 PRs) | No work in either |
| **ReBAC Issues** | ❌ None | ❌ Issues disabled | N/A |
| **ReBAC Branches** | ❌ None | ❌ None | No feature branches |
| **Kessel/SpiceDB Dependencies** | ❌ None in `go.mod` | ❌ None in `go.mod` | Identical |
| **Design Documents** | ❌ None in `/docs` | ❌ None in `/docs` | Identical |
| **Recent Activity** | ✅ Active development (2026-02-02) | ✅ Active development (2025-12-05) | Both active, no ReBAC work |

**Latest Commits (Upstream as of 2026-02-04)**:
- 2026-02-02: Dependency updates (konflux)
- 2026-01-30: Fix failures for sources services
- 2026-01-15: Unleash local setup
- 2025-12-23: Namespace recommendation changes

**Focus Areas (Recent Work)**:
- Dependency management and updates
- Local development improvements
- Namespace recommendations (Kruize integration)
- Kafka lag monitoring
- No authorization/ReBAC work

**Conclusion**: The upstream `RedHatInsights/ros-ocp-backend` repository is actively maintained but has **zero ReBAC work**. The fork (`insights-onprem/ros-ocp-backend`) is in sync with upstream regarding ReBAC status.

---

## What ROS OCP Backend Currently Has

### Authentication/Authorization (NETWORK_POLICY_SECURITY.md)

**Architecture**:
```
Client → JWT Token (Keycloak) → Envoy Sidecar → X-Rh-Identity → Backend
```

**Key Components**:
- JWT validation by Envoy's native `jwt_authn` filter
- Claims extraction to `X-Rh-Identity` headers via Lua script
- Envoy sidecars deployed on services
- Kubernetes NetworkPolicy for metrics endpoints

**This is about authentication (who you are), NOT authorization (what you can do)**

### Current RBAC Integration (rbac.go)

```go
// Calls RBAC API
url := fmt.Sprintf(
    "%s://%s:%s/api/rbac/v1/access/?application=cost-management&limit=100",
    cfg.RBACProtocol, cfg.RBACHost, cfg.RBACPort,
)

// Aggregates permissions by resource type
permissions := map[string][]string{
    "openshift.cluster": ["cluster-1", "cluster-2", "*"],
    "openshift.node": ["*"],
    "openshift.project": ["*"]
}
```

**Same pattern as Koku** - HTTP call to RBAC API, parse response, aggregate permissions.

---

## Detailed Comparison

### 1. ReBAC Design Status

| Aspect | Koku | ROS OCP Backend |
|--------|------|----------------|
| **ReBAC Design Document** | ✅ Complete HLD (991 lines) | ❌ None |
| **Implementation Plan** | ✅ Two-phase approach | ❌ Not started |
| **Schema Definitions** | ✅ Designed (3 OCP resources) | ❌ Not designed |
| **Timeline** | ✅ Defined (16 weeks) | ❌ Unknown |
| **Kessel Integration** | ✅ Planned (adapter pattern) | ❌ Not planned |

### 2. Current Authorization Architecture

| Aspect | Koku | ROS OCP Backend |
|--------|------|----------------|
| **Language** | Python (Django) | Go (Echo framework) |
| **Authorization System** | RBAC API only | RBAC API only |
| **HTTP Client** | Python `requests` | Go `http.Client` |
| **Permission Storage** | `request.user.access` (middleware) | Echo context `c.Set()` |
| **Resource Types** | All providers (AWS, Azure, GCP, OCP, cost models) | OCP only (cluster, node, project) |
| **Permission Cache** | 30 seconds | Unknown (not documented) |

### 3. RBAC API Integration Pattern

**Both teams use IDENTICAL pattern:**

```
1. Receive request with X-Rh-Identity header
2. Call /api/rbac/v1/access/?application=cost-management
3. Parse JSON response
4. Extract resource-level permissions
5. Store in request context
6. Use for filtering/authorization
```

**Key Similarity**: The authorization logic is framework-agnostic. The ReBAC pattern Koku designs could be ported to Go/Echo.

### 4. OpenShift Resource Handling

| Resource Type | Koku Plan | ROS Current |
|--------------|-----------|-------------|
| `openshift.cluster` | ✅ Phase 1 (wildcard), Phase 2 (resource-specific) | ✅ RBAC (wildcard + specific IDs) |
| `openshift.node` | ✅ Phase 1 (wildcard), Phase 2 (resource-specific) | ✅ RBAC (wildcard + specific IDs) |
| `openshift.project` | ✅ Phase 1 (wildcard), Phase 2 (resource-specific) | ✅ RBAC (wildcard + specific IDs) |

**Note**: Both handle the same 3 OCP resource types.

---

## What Koku HLD Has That ROS Does Not

### 1. ReBAC Schema Design

**Koku HLD includes:**
```zed
definition cost_management/openshift_cluster {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation owner: rbac/principal | rbac/group#member
    
    permission view = viewer + owner + org->cost_management_openshift_cluster_read
    permission manage = owner + org->cost_management_openshift_cluster_all
}

definition cost_management/openshift_node {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation cluster: cost_management/openshift_cluster
    
    permission view = viewer + cluster->view + org->cost_management_openshift_node_read
}

definition cost_management/openshift_project {
    relation org: rbac/tenant
    relation viewer: rbac/principal | rbac/group#member
    relation cluster: cost_management/openshift_cluster
    
    permission view = viewer + cluster->view + org->cost_management_openshift_project_read
}
```

**ROS**: Nothing equivalent

### 2. Two-Phase Implementation Strategy

**Koku's approach:**

**Phase 1: Wildcard-Only (0-1 month)**
- Use existing production ReBAC schema
- Org-level permission checks
- No schema changes needed
- 100% RBAC compatibility

**Phase 2: Resource-Specific (2-4 months)**
- Submit schema PR to rbac-config
- Resource-specific permissions
- Ownership and delegation model
- Full ReBAC capabilities

**ROS**: No phased approach planned

### 3. Authorization Service Abstraction

**Koku's adapter pattern:**

```python
class AuthorizationBackend(ABC):
    @abstractmethod
    def has_permission(self, user, resource_type, verb, resource_id=None):
        pass

class RBACAuthorizationBackend(AuthorizationBackend):
    # Current RBAC implementation
    
class KesselAuthorizationBackend(AuthorizationBackend):
    # New Kessel implementation

# Factory function
def get_authorization_service():
    if settings.KOKU_ONPREM_DEPLOYMENT:
        return KesselAuthorizationBackend()
    else:
        return RBACAuthorizationBackend()
```

**Benefits**:
- Transparent switching between RBAC and ReBAC
- No changes to API views or permission classes
- Environment-based selection
- Easy testing with mocks

**ROS**: No abstraction layer designed

### 4. Resource Synchronization Strategy

**Koku's approach:**

**Integration Point**: Sources API → ProviderBuilder

```python
# When OCP provider created
provider = self._create_provider(...)

# Report to Kessel
if provider.type == Provider.PROVIDER_OCP:
    reporter.report_ocp_cluster(
        cluster_id=cluster_id,
        org_id=org_id,
        tenant_id=tenant_id,
        creator_principal=creator
    )
```

**Key Design Decisions**:
- Non-blocking: Kessel failures don't prevent provider operations
- Creator tracking: User who creates provider becomes owner
- Lazy sync for nodes/projects
- Integration with existing lifecycle events

**ROS**: No resource synchronization planned

### 5. Testing Strategy

**Koku HLD includes:**

**Phase 1 Tests**:
- Unit tests for authorization service
- Unit tests for permission classes
- Integration tests for provider creation
- E2E tests for permission checks

**Phase 2 Tests**:
- Resource-specific permission tests
- Hierarchy enforcement tests
- Resource synchronization tests
- Ownership model tests

**ROS**: No testing strategy for ReBAC

### 6. Rollout Plan

**Koku's 16-week plan:**

**Week 1-4**: Phase 1 development and deployment
**Week 5-6**: Schema development and PR submission
**Week 7-10**: External dependency (schema review)
**Week 11-13**: Resource synchronization
**Week 14-15**: Specific permission checks
**Week 16**: Production deployment

**ROS**: No timeline

---

## Key Differences Summary

### Architecture Differences

| Component | Koku | ROS |
|-----------|------|-----|
| **Authorization Abstraction** | ✅ Adapter pattern with factory | ❌ Direct RBAC calls |
| **Backend Selection** | ✅ Environment-based (KOKU_ONPREM_DEPLOYMENT) | ❌ N/A |
| **Resource Sync** | ✅ Sources API integration | ❌ N/A |
| **Permission Caching** | ✅ 30-second TTL (configurable) | ❓ Unknown |
| **Error Handling** | ✅ Fail-closed with logging | ❓ Unknown for ReBAC |

### Scope Differences

| Aspect | Koku | ROS |
|--------|------|-----|
| **Providers** | Multi-cloud (AWS, Azure, GCP, OCP) + Cost Models | OCP only |
| **Resource Types** | 10+ resource types across providers | 3 OCP resource types |
| **Deployment** | SaaS + On-premise | On-premise focused |
| **Schema Complexity** | Complex (multiple provider hierarchies) | Simpler (OCP hierarchy only) |

### Implementation Differences

| Aspect | Koku | ROS |
|--------|------|-----|
| **Language** | Python | Go |
| **Web Framework** | Django REST Framework | Echo |
| **Permission Classes** | Django REST Framework permissions | Echo middleware |
| **SDK** | Kessel Python SDK | Would need Kessel Go SDK |
| **Testing** | Django TestCase + pytest | Go testing package |

---

## What ROS COULD Learn From Koku HLD

### 1. Two-Phase Approach

**Benefit**: Start delivering value immediately without waiting for schema approval.

**Phase 1 for ROS** (if they adopt):
- Keep existing RBAC middleware
- Add Kessel client as alternative backend
- Use environment variable to switch (`ROS_ONPREM_DEPLOYMENT`)
- Call Kessel for org-level permission checks
- **No schema changes needed** - works with existing production schema

**Timeline**: Could be done in 2-4 weeks

### 2. Abstraction Layer

**Current ROS code**:
```go
// Direct RBAC call in middleware
permissions := get_user_permissions_from_rbac(encodedIdentity)
c.Set("user.permissions", permissions)
```

**Proposed with abstraction**:
```go
// Interface
type AuthorizationBackend interface {
    HasPermission(user, resourceType, verb, resourceID) bool
}

// Implementations
type RBACBackend struct{}
type KesselBackend struct{}

// Factory
func GetAuthorizationService() AuthorizationBackend {
    if config.OnPremDeployment {
        return &KesselBackend{}
    }
    return &RBACBackend{}
}

// Usage in middleware
authService := GetAuthorizationService()
if authService.HasPermission(user, "openshift.cluster", "read", "") {
    // allow
}
```

**Benefits**:
- Same middleware code for both backends
- Easy testing with mocks
- Clean separation of concerns
- No changes to handler code

### 3. Schema Coordination

**Koku is submitting 3 OCP resource definitions**:
- `cost_management/openshift_cluster`
- `cost_management/openshift_node`
- `cost_management/openshift_project`

**ROS needs the EXACT SAME definitions** for their OCP resources.

**Opportunity**: Coordinate schema submission with Koku team to:
- Submit together to rbac-config
- Share review timeline
- Test with same schema
- Reduce duplication of effort

### 4. Resource Synchronization Pattern

**Koku's pattern** (adaptable to Go):

```go
// In provider creation handler
func CreateProvider(c echo.Context) error {
    // ... create provider ...
    
    // Report to Kessel
    if provider.Type == "OCP" && config.OnPremDeployment {
        reporter := NewKesselResourceReporter()
        err := reporter.ReportOCPCluster(
            clusterID,
            orgID,
            tenantID,
            creatorPrincipal,
        )
        if err != nil {
            log.Warn("Failed to report cluster to Kessel", err)
            // Don't fail provider creation
        }
    }
    
    return c.JSON(http.StatusCreated, provider)
}
```

**Key design**: Non-blocking, logged failures

---

## Recommendations

### For Koku Team

1. **Proceed with HLD implementation** - ROS has no conflicting design
2. **Share HLD with ROS team** - Could save them months of design work
3. **Coordinate schema submission** - Both need same OCP definitions
4. **Offer collaboration** - Pattern is framework-agnostic

### For ROS Team (if they want ReBAC)

1. **Adopt Koku's phased approach** - Start with Phase 1 (wildcard)
2. **Implement authorization abstraction** - Interface + factory pattern
3. **Coordinate with Koku** - Submit schema together
4. **Use Kessel Go SDK** - Similar patterns to Python SDK
5. **Leverage Koku's testing strategy** - Adapt to Go testing

### For Both Teams

1. **Schema coordination** - Submit 3 OCP definitions together
2. **Timeline alignment** - Coordinate Phase 2 schema review
3. **Testing coordination** - Same Kessel instance for testing
4. **Documentation sharing** - Architecture patterns apply to both

---

## Conclusion

### Current State

| Team | ReBAC Status | Design | Timeline |
|------|--------------|--------|----------|
| **Koku** | HLD complete, ready to implement | ✅ 991-line HLD + implementation guide | 16 weeks planned |
| **ROS** | Not started, no design | ❌ None | Unknown |

### Key Findings

1. **No conflict**: ROS has no ReBAC design to conflict with Koku's approach
2. **Same patterns**: Both teams use identical RBAC integration today
3. **Same resources**: Both need the same 3 OCP resource definitions
4. **Framework-agnostic**: Koku's design patterns work in Go/Echo
5. **Collaboration opportunity**: Koku can lead, ROS can follow similar approach

### Strategic Recommendation

**Koku should proceed with implementation and actively share the design with ROS team.**

The authorization abstraction pattern is language/framework-agnostic and could save ROS team significant design effort if they decide to implement ReBAC in the future.

---

**Document Version**: 1.1  
**Last Updated**: 2026-02-04  
**Repositories Analyzed**:
- **Koku**: `/Users/jgil/go/src/github.com/insights-onprem/koku`
- **ROS Upstream**: https://github.com/RedHatInsights/ros-ocp-backend (verified 2026-02-04)
- **ROS Fork**: https://github.com/insights-onprem/ros-ocp-backend (verified 2026-01-30)

**Comparison Based On**:
- Koku HLD: `docs/architecture/kessel-ocp-integration.md`
- ROS Investigation: `docs/architecture/ros-ocp-backend-rebac-status.md`

**Latest ROS Commits Checked**:
- Upstream: 2026-02-02 (red-hat-konflux[bot] - "chore(deps): update konflux references")
- Upstream: 2026-01-30 (kgaikwad - "Fix failures for sources services in local setup")
- No ReBAC-related work found in recent activity
