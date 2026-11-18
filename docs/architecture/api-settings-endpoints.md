# Settings API Endpoints Documentation

## Overview

The Settings API provides endpoints for managing user preferences, tag configurations, cost groups, and AWS category keys. These settings control how cost data is displayed, filtered, and aggregated across the Koku platform.

All settings endpoints require authentication and appropriate permissions (`SettingsAccessPermission`).

**Base Path:** `/api/v1/`

---

## Account Settings

### **Purpose**
Manage user-level preferences for currency display and AWS cost calculation methods.

### **Endpoints**

#### Get All Account Settings
```
GET /account-settings/
```

**Response:**
```json
{
  "meta": {
    "count": 2
  },
  "data": [
    {
      "currency": "USD",
      "cost_type": "unblended_cost"
    }
  ]
}
```

#### Get Specific Setting
```
GET /account-settings/{setting}/
```

**Path Parameters:**
- `setting` - Setting name: `currency` or `cost-type`

**Response:**
```json
{
  "meta": {
    "count": 1
  },
  "data": [
    {
      "currency": "USD"
    }
  ]
}
```

#### Update Setting
```
PUT /account-settings/{setting}/
```

**Request Body (Currency):**
```json
{
  "currency": "EUR"
}
```

**Request Body (Cost Type):**
```json
{
  "cost_type": "calculated_amortized_cost"
}
```

**Response:** `204 No Content`

### **Available Settings**

#### Currency
Display currency preference for cost data.

**Supported Values:**
- `USD` - US Dollar
- `EUR` - Euro
- `GBP` - British Pound
- `JPY` - Japanese Yen
- And other ISO 4217 currency codes

**Effect:** Invalidates **all** cached views for the tenant when changed.

#### Cost Type
AWS cost calculation method.

**Supported Values:**

| Code                        | Name      | Description                                                            |
| --------------------------- | --------- | ---------------------------------------------------------------------- |
| `unblended_cost`            | Unblended | Usage cost on the day you are charged (default)                        |
| `calculated_amortized_cost` | Amortized | Recurring and/or upfront costs are distributed evenly across the month |
| `blended_cost`              | Blended   | Using a blended rate to calculate cost usage                           |

**Effect:** Invalidates **AWS** cached views for the tenant when changed.

### **Default Values**
- `currency`: `USD`
- `cost_type`: `unblended_cost`

---

## Tag Settings

### **Purpose**
Manage which tags/labels are tracked and available for filtering in cost reports. Tags must be enabled before they appear in filter dropdowns and group-by options.

### **Endpoints**

#### List Tags
```
GET /settings/tags/
```

**Query Parameters:**
- `key` (string) - Filter by tag key name (case-insensitive, supports partial match)
- `uuid` (string) - Filter by tag UUID
- `provider_type` / `source_type` (string) - Filter by provider: `AWS`, `Azure`, `GCP`, `OCP`, `OCP-AWS`, `OCP-Azure`, `OCP-GCP`
- `enabled` (boolean) - Filter by enabled status
- `limit` (integer) - Results per page (default: 10)
- `offset` (integer) - Pagination offset

**Response:**
```json
{
  "meta": {
    "count": 150,
    "enabled_tags_count": 42,
    "enabled_tags_limit": 200
  },
  "links": {
    "first": "/api/v1/settings/tags/?limit=10&offset=0",
    "next": "/api/v1/settings/tags/?limit=10&offset=10",
    "previous": null,
    "last": "/api/v1/settings/tags/?limit=10&offset=140"
  },
  "data": [
    {
      "uuid": "abc123-def456-ghi789",
      "key": "environment",
      "enabled": true,
      "provider_type": "AWS"
    },
    {
      "uuid": "xyz987-uvw654-rst321",
      "key": "cost_center",
      "enabled": false,
      "provider_type": "AWS"
    }
  ]
}
```

#### Enable Tags
```
PUT /settings/tags/enable/
```

**Request Body:**
```json
{
  "ids": [
    "abc123-def456-ghi789",
    "xyz987-uvw654-rst321"
  ]
}
```

**Response:** `204 No Content`

**Error Responses:**

**Tag Limit Exceeded (412 Precondition Failed):**
```json
{
  "error": "The maximum number of enabled tags is 200.",
  "enabled": 195,
  "limit": 200
}
```

#### Disable Tags
```
PUT /settings/tags/disable/
```

**Request Body:**
```json
{
  "ids": [
    "abc123-def456-ghi789"
  ]
}
```

**Response:** `204 No Content`

**Error Responses:**

**Tag Involved in Mapping (412 Precondition Failed):**
```json
{
  "error": "Can not disable a key associated with a tag mapping",
  "ids": [
    "abc123-def456-ghi789"
  ]
}
```

### **Tag Limit**
- **Configurable Limit:** Controlled by `ENABLED_TAG_LIMIT` environment variable (default: 200)
- **Rationale:** Limiting enabled tags improves query performance and reduces database index size
- **Tracking:** The response includes `enabled_tags_count` and `enabled_tags_limit` in metadata

### **Tag Protection Rules**
1. Tags used in tag mappings (as parent or child) **cannot be disabled**
2. Must remove the tag mapping first, then disable the tag

---

## Tag Mappings

### **Purpose**
Create parent-child relationships between tags for unified reporting. This allows you to aggregate costs across multiple tag values under a single parent tag.

**Use Case Example:**
- Parent: `department:engineering`
- Children: `team:frontend`, `team:backend`, `team:platform`, `team:devops`
- Result: View all engineering costs aggregated under `department:engineering`

### **Endpoints**

#### List Tag Mappings
```
GET /settings/tags/mappings/
```

**Query Parameters:**
- `parent` (string) - Filter by parent tag key
- `child` (string) - Filter by child tag key
- `source_type` (string) - Filter by provider type
- `limit` (integer) - Results per page
- `offset` (integer) - Pagination offset

**Response:**
```json
{
  "meta": {
    "count": 5
  },
  "links": {
    "first": "/api/v1/settings/tags/mappings/?limit=10&offset=0",
    "next": null,
    "previous": null,
    "last": "/api/v1/settings/tags/mappings/?limit=10&offset=0"
  },
  "data": [
    {
      "parent": {
        "uuid": "parent-uuid-1",
        "key": "department",
        "provider_type": "AWS"
      },
      "children": [
        {
          "uuid": "child-uuid-1",
          "key": "team",
          "value": "frontend",
          "provider_type": "AWS"
        },
        {
          "uuid": "child-uuid-2",
          "key": "team",
          "value": "backend",
          "provider_type": "AWS"
        }
      ]
    }
  ]
}
```

#### List Available Parent Tags
```
GET /settings/tags/mappings/parent/
```

Returns enabled tags that are eligible to be parent tags (not already children, not involved in cost models).

**Query Parameters:**
- `key` (string) - Filter by tag key
- `source_type` (string) - Filter by provider type

**Response:**
```json
{
  "meta": {
    "count": 25
  },
  "data": [
    {
      "uuid": "tag-uuid-1",
      "key": "department",
      "provider_type": "AWS",
      "cost_model_id": null
    }
  ]
}
```

#### List Available Child Tags
```
GET /settings/tags/mappings/child/
```

Returns enabled tags that are eligible to be child tags (not already parents, not already children of another parent).

**Query Parameters:**
- `key` (string) - Filter by tag key
- `source_type` (string) - Filter by provider type

**Response:**
```json
{
  "meta": {
    "count": 50
  },
  "data": [
    {
      "uuid": "tag-uuid-2",
      "key": "team",
      "provider_type": "AWS",
      "cost_model_id": null
    }
  ]
}
```

#### Add Child Tags to Parent
```
PUT /settings/tags/mappings/child/add/
```

**Request Body:**
```json
{
  "parent": "parent-uuid-1",
  "children": [
    "child-uuid-1",
    "child-uuid-2",
    "child-uuid-3"
  ]
}
```

**Response:** `204 No Content`

**Effect:** Triggers re-summarization of the current month's data for affected providers.

#### Remove Child Tag Mappings
```
PUT /settings/tags/mappings/child/remove/
```

**Request Body:**
```json
{
  "ids": [
    "child-uuid-1",
    "child-uuid-2"
  ]
}
```

**Response:** `204 No Content`

**Effect:** Triggers re-summarization of the current month's data for affected providers.

#### Remove Parent Tag Mapping (and all children)
```
PUT /settings/tags/mappings/parent/remove/
```

**Request Body:**
```json
{
  "ids": [
    "parent-uuid-1"
  ]
}
```

**Response:** `204 No Content`

**Effect:** Removes the entire parent-child relationship. Triggers re-summarization for all affected child tags.

### **Tag Mapping Rules**

1. **Enabled Only:** Only enabled tags can participate in mappings
2. **No Multi-Level:** A tag cannot be both a parent and a child
3. **Single Parent:** A child tag can only have one parent
4. **No Cost Model Children:** Tags used in cost models with tag-based rates cannot be children
5. **Provider Match:** Parent and children must be from the same provider type
6. **Automatic Re-summarization:** Changes trigger Celery tasks to re-summarize current month data

### **Cost Model Integration**
- If a parent tag is used in an OCP cost model with tag-based rates, the mapping is taken into account
- Child tag costs are aggregated under the parent tag in reports
- The `cost_model_id` field indicates which cost model uses the tag

---

## AWS Category Keys

### **Purpose**
Manage AWS Cost Categories - custom groupings for AWS costs defined in AWS Cost Management Console. Only enabled category keys appear as filter options in AWS reports.

**Note:** AWS Cost Categories are defined in your AWS account. Koku discovers them from Cost and Usage Reports (CUR).

### **Endpoints**

#### List AWS Category Keys
```
GET /settings/aws_category_keys/
```

**Query Parameters:**
- `key` (string) - Filter by category key name
- `uuid` (string) - Filter by UUID
- `enabled` (boolean) - Filter by enabled status
- `limit` (integer) - Results per page
- `offset` (integer) - Pagination offset

**Response:**
```json
{
  "meta": {
    "count": 10
  },
  "links": {
    "first": "/api/v1/settings/aws_category_keys/?limit=10&offset=0",
    "next": null,
    "previous": null,
    "last": "/api/v1/settings/aws_category_keys/?limit=10&offset=0"
  },
  "data": [
    {
      "uuid": "category-uuid-1",
      "key": "BusinessUnit",
      "enabled": true
    },
    {
      "uuid": "category-uuid-2",
      "key": "CostCenter",
      "enabled": false
    }
  ]
}
```

#### Enable AWS Category Keys
```
PUT /settings/aws_category_keys/enable/
```

**Request Body:**
```json
{
  "ids": [
    "category-uuid-1",
    "category-uuid-2"
  ]
}
```

**Response:** `204 No Content`

**Effect:** Invalidates AWS cached views for the tenant.

#### Disable AWS Category Keys
```
PUT /settings/aws_category_keys/disable/
```

**Request Body:**
```json
{
  "ids": [
    "category-uuid-1"
  ]
}
```

**Response:** `204 No Content`

**Effect:** Invalidates AWS cached views for the tenant.

### **AWS Cost Categories vs Tags**
- **Tags:** User-defined key-value pairs on AWS resources
- **Cost Categories:** AWS-managed groupings defined in Cost Management
- Both can be used for cost allocation and filtering
- Cost Categories provide more structured, rule-based groupings

---

## Cost Groups (OpenShift)

### **Purpose**
Manage OpenShift namespace cost group assignments. Namespaces can be assigned to the **Platform** cost group to separate infrastructure costs from application workload costs.

### **Cost Group Types**

| Group            | Description                          | Examples                                           |
| ---------------- | ------------------------------------ | -------------------------------------------------- |
| **Platform**     | Infrastructure and platform services | kube-system, openshift-*, istio-system, monitoring |
| **Worker**       | Application workloads                | app namespaces, customer workloads                 |
| **Unattributed** | Costs not allocated to any namespace | Unallocated node costs, platform overhead          |

### **Endpoints**

#### List Cost Group Assignments
```
GET /settings/cost-groups/
```

**Query Parameters:**
- `filter[project]` (string or list) - Filter by project/namespace name
- `filter[group]` (string or list) - Filter by cost group: `Platform`, `Worker`
- `filter[default]` (boolean) - Filter by default status (true/false)
- `filter[cluster]` (string or list) - Filter by cluster ID or alias
- `exclude[project]` (string) - Exclude specific projects
- `exclude[group]` (string) - Exclude specific cost groups
- `exclude[default]` (boolean) - Exclude default projects
- `exclude[cluster]` (string or list) - Exclude specific clusters
- `order_by[project]` (string) - Order by project name: `asc` or `desc`
- `order_by[group]` (string) - Order by group: `asc` or `desc`
- `order_by[default]` (string) - Order by default status: `asc` or `desc`
- `limit` (integer) - Results per page
- `offset` (integer) - Pagination offset

**Example Queries:**
```
GET /settings/cost-groups/?filter[group]=Platform
GET /settings/cost-groups/?filter[cluster]=my-cluster&filter[default]=false
GET /settings/cost-groups/?filter[project]=istio-system,monitoring
GET /settings/cost-groups/?exclude[default]=true&order_by[project]=asc
```

**Response:**
```json
{
  "meta": {
    "count": 15
  },
  "data": [
    {
      "project": "kube-system",
      "group": "Platform",
      "default": true
    },
    {
      "project": "openshift-monitoring",
      "group": "Platform",
      "default": true
    },
    {
      "project": "istio-system",
      "group": "Platform",
      "default": false
    },
    {
      "project": "my-app",
      "group": "Worker",
      "default": false
    }
  ]
}
```

#### Add Namespaces to Platform Cost Group
```
PUT /settings/cost-groups/add/
```

**Request Body:**
```json
[
  {
    "project": "istio-system",
    "group": "Platform"
  },
  {
    "project": "monitoring",
    "group": "Platform"
  }
]
```

**Response:** `204 No Content`

**Note:** The `default` field is read-only and automatically determined by the system based on whether the namespace is a built-in system namespace (e.g., `kube-*`, `openshift-*`).

**Effect:**
1. Namespaces are marked as Platform
2. Triggers async re-summarization of current month's OCP data
3. Returns list of affected OCP provider UUIDs in background job

#### Remove Namespaces from Platform Cost Group
```
PUT /settings/cost-groups/remove/
```

**Request Body:**
```json
[
  {
    "project": "istio-system",
    "group": "Worker"
  }
]
```

**Response:** `204 No Content`

**Effect:**
1. Namespaces are moved to Worker group
2. Triggers async re-summarization of current month's OCP data

### **Default Namespaces**
The following namespaces are **default Platform** and **cannot be removed**:
- `kube-*` (kube-system, kube-public, etc.)
- `openshift-*` (all OpenShift system namespaces)
- Other system namespaces as defined by cluster

**Trying to remove default namespaces will result in validation error.**

### **Cost Allocation Impact**

**Platform Namespaces:**
- Costs are categorized as infrastructure/platform
- Not charged back to application teams
- Reported separately in Platform cost breakdowns

**Worker Namespaces:**
- Costs are categorized as application workload
- Can be charged back to teams/projects
- Used for showback/chargeback reporting

### **Re-summarization Process**
1. **Identify Affected Providers:** Find all OCP providers that have the specified namespaces
2. **Queue Celery Tasks:** Submit `update_summary_tables` tasks for each provider
3. **Process Current Month:** Re-summarize OCP data for the current month only
4. **Update UI Summaries:** Refresh pre-aggregated tables for faster API queries

**Typical Re-summarization Time:** 5-15 minutes per cluster, depending on cluster size.

---

## Common Features

### **Pagination**
All `GET` endpoints support pagination with consistent parameters:

**Parameters:**
- `limit` (integer, default: 10) - Number of results per page
- `offset` (integer, default: 0) - Number of results to skip

**Response Format:**
```json
{
  "meta": {
    "count": 150
  },
  "links": {
    "first": "...",
    "next": "...",
    "previous": "...",
    "last": "..."
  },
  "data": [...]
}
```

### **Filtering**
Most endpoints support multiple query parameter filters:
- Filters can be combined (AND logic)
- Multiple values for the same parameter use OR logic
- Case-insensitive matching for string fields

**Example:**
```
GET /settings/tags/?provider_type=AWS&provider_type=GCP&enabled=true
```
Returns enabled tags from AWS **or** GCP.

### **Caching**
- All settings endpoints use `@never_cache` decorator
- Changes to settings invalidate relevant cached views:
  - **Currency changes:** Invalidate all cached views for tenant
  - **Cost type changes:** Invalidate AWS cached views
  - **Tag/category changes:** Invalidate provider-specific cached views

### **Authentication & Permissions**
- **Authentication:** Required (Bearer token or session)
- **Permission:** `SettingsAccessPermission` (typically maps to `cost-management:settings:*` RBAC permissions)
- **Multi-tenancy:** All data is automatically scoped to the authenticated user's customer/schema

### **Response Codes**

| Code | Status                | Usage                                              |
| ---- | --------------------- | -------------------------------------------------- |
| 200  | OK                    | Successful GET request                             |
| 204  | No Content            | Successful PUT request (no response body)          |
| 400  | Bad Request           | Invalid request body or parameters                 |
| 401  | Unauthorized          | Missing or invalid authentication                  |
| 403  | Forbidden             | Insufficient permissions                           |
| 404  | Not Found             | Invalid setting name or resource not found         |
| 405  | Method Not Allowed    | HTTP method not supported for endpoint             |
| 412  | Precondition Failed   | Business rule violation (e.g., tag limit exceeded) |
| 500  | Internal Server Error | Unexpected server error                            |

---

## Best Practices

### **Enabling Tags**
1. **Start Conservative:** Enable only tags you actively use for filtering/grouping
2. **Monitor Limit:** Keep track of `enabled_tags_count` vs `enabled_tags_limit`
3. **Regular Cleanup:** Disable unused tags to free up slots
4. **Provider-Specific:** Enable tags per provider based on your reporting needs

### **Tag Mappings**
1. **Plan Hierarchy:** Design parent-child relationships before creating mappings
2. **Single Level:** Keep mappings to one level (parent → children) for simplicity
3. **Consistent Naming:** Use consistent tag key naming conventions
4. **Test First:** Create mappings in non-production before rolling out
5. **Monitor Re-summarization:** Watch for Celery task completion after changes

### **Cost Groups**
1. **Define Strategy:** Establish clear criteria for Platform vs Worker classification
2. **Document Decisions:** Keep a record of which namespaces are Platform and why
3. **Communicate Changes:** Inform stakeholders before reclassifying namespaces
4. **Timing:** Make changes during low-usage periods to minimize re-summarization impact

### **AWS Category Keys**
1. **Align with AWS:** Keep Koku categories in sync with your AWS Cost Category definitions
2. **Enable Selectively:** Only enable categories used in reports to reduce clutter
3. **Test Filters:** Verify category filters work correctly after enabling

---

## Troubleshooting

### **Tag Limit Exceeded**
**Problem:** Cannot enable more tags, receiving 412 error.

**Solutions:**
1. Disable unused tags to free up slots
2. Contact administrator to increase `ENABLED_TAG_LIMIT`
3. Prioritize most important tags for cost allocation

### **Cannot Disable Tag**
**Problem:** Tag disable fails with "associated with a tag mapping" error.

**Solutions:**
1. Check `/settings/tags/mappings/` to find which mapping uses the tag
2. Remove the tag mapping first
3. Then disable the tag

### **Cost Group Changes Not Reflected**
**Problem:** Namespace cost group changes not showing in reports.

**Solutions:**
1. Check Celery worker logs for re-summarization task status
2. Verify task completed successfully
3. Wait 5-15 minutes for processing to complete
4. Refresh UI/clear browser cache
5. Check date range in report (only current month is re-summarized)

### **Tag Mapping Not Aggregating Costs**
**Problem:** Parent tag not showing aggregated child costs.

**Solutions:**
1. Verify all tags (parent + children) are **enabled**
2. Check that parent and children are from same provider type
3. Wait for re-summarization to complete
4. Verify date range is in current month (historical data not re-processed)

### **Performance Issues After Enabling Many Tags**
**Problem:** Reports slow down after enabling many tags.

**Solutions:**
1. Disable unused tags
2. Avoid enabling all tags from all providers
3. Use tag mappings to reduce number of enabled tags
4. Contact administrator about database index optimization

---

## API Examples

### **Python (requests)**

```python
import requests

BASE_URL = "https://console.redhat.com/api/cost-management/v1"
TOKEN = "your-bearer-token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Get account settings
response = requests.get(f"{BASE_URL}/account-settings/", headers=headers)
settings = response.json()
print(f"Current currency: {settings['data'][0]['currency']}")

# Enable tags
payload = {
    "ids": ["tag-uuid-1", "tag-uuid-2"]
}
response = requests.put(
    f"{BASE_URL}/settings/tags/enable/",
    headers=headers,
    json=payload
)
print(f"Tags enabled: {response.status_code == 204}")

# Create tag mapping
payload = {
    "parent": "parent-uuid",
    "children": ["child-uuid-1", "child-uuid-2"]
}
response = requests.put(
    f"{BASE_URL}/settings/tags/mappings/child/add/",
    headers=headers,
    json=payload
)
print(f"Mapping created: {response.status_code == 204}")
```

### **cURL**

```bash
# Get enabled tags
curl -X GET \
  "https://console.redhat.com/api/cost-management/v1/settings/tags/?enabled=true" \
  -H "Authorization: Bearer $TOKEN"

# Update currency
curl -X PUT \
  "https://console.redhat.com/api/cost-management/v1/account-settings/currency/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"currency": "EUR"}'

# Add namespace to Platform cost group
curl -X PUT \
  "https://console.redhat.com/api/cost-management/v1/settings/cost-groups/add/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"project": "istio-system", "group": "Platform"}]'
```

---

## Related Documentation

- **Tag Management:** See tag filtering and grouping in report APIs
- **Cost Models:** Tag-based cost allocation for OpenShift
- **RBAC Permissions:** Settings access control configuration
- **Cost Allocation:** Understanding Platform vs Worker costs

---

## Document Metadata

- **Last Updated:** 2025-01-21
- **API Version:** v1
- **Koku Version:** Current
- **Author:** Architecture Documentation Team
