# API Architecture: Serializers, Provider Maps, and Endpoints

This document describes the relationship between serializers, provider maps, and API endpoints in the Koku API architecture, explaining how these components work together to provide cost and usage reporting.

## Table of Contents

- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Component Responsibilities](#component-responsibilities)
- [Serializers](#serializers)
- [Provider Maps](#provider-maps)
- [Query Handlers](#query-handlers)
- [API Views and Endpoints](#api-views-and-endpoints)
- [Data Flow](#data-flow)
- [Provider-Specific Implementations](#provider-specific-implementations)
- [Adding New Endpoints](#adding-new-endpoints)

---

## Overview

The Koku API uses a layered architecture where serializers, provider maps, query handlers, and views work together to provide a flexible and maintainable reporting API. This design allows us to:

1. **Support multiple cloud providers** (AWS, Azure, GCP, OpenShift) with consistent APIs
2. **Validate and normalize** user input consistently
3. **Map API parameters** to database fields dynamically
4. **Query different data models** based on report type and provider
5. **Format responses** consistently across all endpoints

### Key Concepts

- **Serializers**: Validate and transform API request parameters
- **Provider Maps**: Define mappings between API parameters, database models, and query configurations
- **Query Handlers**: Execute database queries using the provider maps
- **Views**: Tie everything together and expose HTTP endpoints

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         HTTP Request                                    │
│                    GET /api/v1/reports/aws/costs/                       │
│                    ?group_by[account]=*&filter[region]=us-east-1        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          URL Router                                     │
│                      (koku/api/urls.py)                                 │
│   Routes to: AWSCostView (report/aws/view.py)                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ReportView (Base View)                             │
│                     (report/view.py)                                    │
│  Properties:                                                            │
│  - provider = Provider.PROVIDER_AWS                                     │
│  - report = "costs"                                                     │
│  - serializer = AWSQueryParamSerializer                                 │
│  - query_handler = AWSReportQueryHandler                                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    QueryParameters Object                               │
│                   (api/query_params.py)                                 │
│  - Extracts request parameters                                          │
│  - Passes to serializer for validation                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 AWSQueryParamSerializer                                 │
│              (report/aws/serializers.py)                                │
│  Validates:                                                             │
│  - filter (AWSFilterSerializer)                                         │
│  - group_by (AWSGroupBySerializer)                                      │
│  - order_by (AWSOrderBySerializer)                                      │
│  - exclude (AWSExcludeSerializer)                                       │
│  - Tag keys, AWS categories                                             │
│                                                                         │
│  Returns: Validated parameter dictionary                                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              AWSReportQueryHandler                                      │
│           (report/aws/query_handler.py)                                 │
│  Initializes:                                                           │
│  - AWSProviderMap (provider_map.py)                                     │
│  - Determines database models                                           │
│  - Builds query filters and annotations                                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AWSProviderMap                                       │
│              (report/aws/provider_map.py)                               │
│  Provides:                                                              │
│  - Database model selection (query_table)                               │
│  - Field mappings (annotations, filters)                                │
│  - Aggregation definitions (sum_columns)                                │
│  - Report-specific configurations (costs, storage, etc.)                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 Django ORM Query Execution                              │
│  - Selects from: AWSCostSummaryP, AWSCostSummaryByAccountP, etc.        │
│  - Applies filters, aggregations, groupings                             │
│  - Returns QuerySet                                                     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Query Handler Processing                             │
│  - Formats data into API response structure                             │
│  - Applies pagination                                                   │
│  - Adds metadata (total, filter, group_by, order_by)                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         HTTP Response                                   │
│  {                                                                      │
│    "meta": {...},                                                       │
│    "links": {...},                                                      │
│    "data": [...]                                                        │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### 1. Serializers
**Location**: `koku/api/report/<provider>/serializers.py`

**Purpose**: Validate and transform HTTP request parameters into Python data structures.

**Responsibilities**:
- Validate parameter types and values
- Enforce business rules (e.g., "start_date must be before end_date")
- Support dynamic fields (tags, AWS categories)
- Provide clear error messages for invalid input

### 2. Provider Maps
**Location**: `koku/api/report/<provider>/provider_map.py`

**Purpose**: Define the mapping between API concepts and database implementation.

**Responsibilities**:
- Map API parameter names to database field names
- Define which Django models to query
- Specify aggregation functions (Sum, Max, etc.)
- Configure report-specific behavior
- Select appropriate database views/tables based on group_by parameters

### 3. Query Handlers
**Location**: `koku/api/report/<provider>/query_handler.py`

**Purpose**: Execute database queries using provider maps and validated parameters.

**Responsibilities**:
- Build Django ORM queries
- Apply filters, groupings, and orderings
- Format query results into API response structure
- Handle special cases (org units, wildcards, etc.)

### 4. Views
**Location**: `koku/api/report/<provider>/view.py`

**Purpose**: Expose HTTP endpoints and tie components together.

**Responsibilities**:
- Define URL patterns
- Specify permissions
- Set provider and report type
- Handle HTTP methods (GET, POST, etc.)

---

## Serializers

### Serializer Hierarchy

```
BaseSerializer (base validation logic)
    │
    ├── FilterSerializer (filtering parameters)
    │   └── AWSFilterSerializer
    │   └── AzureFilterSerializer
    │   └── GCPFilterSerializer
    │   └── OCPFilterSerializer
    │
    ├── GroupSerializer (group_by parameters)
    │   └── AWSGroupBySerializer
    │   └── AzureGroupBySerializer
    │   └── GCPGroupBySerializer
    │   └── OCPGroupBySerializer
    │
    ├── OrderSerializer (order_by parameters)
    │   └── AWSOrderBySerializer
    │   └── AzureOrderBySerializer
    │   └── GCPOrderBySerializer
    │   └── OCPOrderBySerializer
    │
    ├── ExcludeSerializer (exclude parameters)
    │   └── AWSExcludeSerializer
    │   └── AzureExcludeSerializer
    │   └── GCPExcludeSerializer
    │   └── OCPExcludeSerializer
    │
    └── ParamSerializer (top-level parameters)
        └── ReportQueryParamSerializer
            └── AWSQueryParamSerializer
            └── AzureQueryParamSerializer
            └── GCPQueryParamSerializer
            └── OCPQueryParamSerializer
```

### Serializer Composition

Each provider's query parameter serializer (e.g., [`AWSQueryParamSerializer`](../../koku/api/report/aws/serializers.py)) composes the four sub-serializers:
- `GROUP_BY_SERIALIZER` - Handles group_by parameters
- `ORDER_BY_SERIALIZER` - Handles order_by parameters
- `FILTER_SERIALIZER` - Handles filter parameters
- `EXCLUDE_SERIALIZER` - Handles exclude parameters
- Provider-specific fields (e.g., `delta`, `cost_type` for AWS)

### Key Serializer Features

#### 1. Dynamic Field Support

Serializers (e.g., [`AWSFilterSerializer`](../../koku/api/report/aws/serializers.py)) support dynamic tag and AWS category fields:
- Static fields defined in the class (e.g., `account`, `service`, `region`)
- Dynamic fields added at runtime based on enabled tags and categories
- Configured via `_opfields` tuple and `_aws_category` flag
- Dynamic field examples: `tag:app`, `tag:environment`, `aws_category:project`

#### 2. Operator Prefixes

Serializers support operator prefixes for advanced filtering. Fields listed in `_opfields` automatically generate variants:
- Base field (e.g., `account`)
- `and:field` - Intersection operator
- `or:field` - Union operator
- `exact:field` - Exact match (no partial matching)

Example API usage:
```
?filter[and:account]=123456&filter[and:account]=789012  # Intersection
?filter[or:account]=123456&filter[or:account]=789012    # Union
?filter[exact:account]=123456                           # Exact match (no partial)
```

#### 3. Validation Logic

**Common Validations** (in `BaseSerializer` and `ParamSerializer`):
- Unknown fields are rejected
- start_date must be before end_date
- start_date and end_date cannot be used with time_scope_value/time_scope_units
- order_by requires matching group_by (in most cases)

**Provider-Specific Validations**: Provider serializers implement custom validation methods (e.g., [`AWSGroupBySerializer.validate_group_by()`](../../koku/api/report/aws/serializers.py)) that enforce provider-specific rules such as:
- Org unit validation rules (cannot mix `org_unit_id` and `or:org_unit_id`)
- Endpoint-specific restrictions (e.g., certain fields only valid for costs endpoint)
- Wildcard usage restrictions

---

## Provider Maps

### Provider Map Structure

A provider map ([`AWSProviderMap`](../../koku/api/report/aws/provider_map.py), [`AzureProviderMap`](../../koku/api/report/azure/provider_map.py), etc.) defines how API parameters map to database operations through a `_mapping` dictionary containing:
- **annotations**: Maps API parameter names to database field names (e.g., `account` → `usage_account_id`)
- **filters**: Defines filter operations and field mappings for each parameter
- **group_by_options**: Lists valid group_by fields for the provider
- **tag_column** / **aws_category_column**: Specifies JSON columns for tags and categories
- **report_type**: Configuration for each report type (costs, instance_type, storage, etc.)
- **tables**: Database models to query

### Report Type Configurations

Each report type within a provider map has its own configuration (see [provider_map.py files](../../koku/api/report/)) containing:
- **aggregates**: Django ORM aggregation functions (e.g., `Sum`, `Max`, `Avg`) for query-level aggregations
- **annotations**: Per-row field annotations using Django F() expressions and functions
- **filter**: Static filters applied to all queries for this report type
- **cost_units_key** / **cost_units_fallback**: Currency configuration
- **sum_columns**: Columns that should be summed in responses
- **default_ordering**: Default sort order for results

### View Selection

Provider maps include a `views` dictionary ([see provider_map.py files](../../koku/api/report/)) that selects optimized database views based on group_by parameters.

**How it works**:
1. Query handler determines which parameters are in group_by
2. Creates a tuple of sorted group_by keys: `("account", "service")`
3. Looks up that tuple in the views dictionary
4. Uses the corresponding optimized database view/table for better query performance

Examples: `default` view for no grouping, `AWSCostSummaryByAccountP` for `group_by[account]`, etc.

### Filter Composition

Provider maps support complex filter definitions where a single API parameter can map to multiple database fields. Filters sharing the same `composition_key` are combined with OR logic, allowing searches across multiple fields (e.g., searching "account" can match either `account_alias__account_alias` OR `usage_account_id`).

### Aggregations and Annotations

**Aggregates**: Applied to the entire queryset at the GROUP BY level using Django ORM functions like `Sum()`, `Max()`, `Avg()`. Example: summing `unblended_cost` and `markup_cost` for total cost.

**Annotations**: Applied per-row before grouping using Django F() expressions and functions like `Coalesce()`, `TruncDay()`, etc. Example: normalizing currency codes or truncating dates.

---

## Query Handlers

### Query Handler Hierarchy

```
QueryHandler (base query logic)
    └── ReportQueryHandler (report-specific logic)
        ├── AWSReportQueryHandler
        ├── AzureReportQueryHandler
        ├── GCPReportQueryHandler
        └── OCPReportQueryHandler
            └── OCPAWSReportQueryHandler (OCP on Cloud)
            └── OCPAzureReportQueryHandler
            └── OCPGCPReportQueryHandler
```

### Query Handler Initialization

Query handlers ([`AWSReportQueryHandler`](../../koku/api/report/aws/query_handler.py), etc.) initialize by:
1. Creating a provider map instance with request parameters (provider, report_type, schema_name, cost_type)
2. Extracting group_by options from the provider map
3. Calling parent `ReportQueryHandler` initialization

### Query Building Process

The query handler builds Django ORM queries through several steps (see [`ReportQueryHandler`](../../koku/api/report/query_handler.py)):

1. **Determine Query Table**: Selects the appropriate database model/view from the provider map
2. **Build Annotations**: Creates field annotations for dates, currency, group_by fields, and tags using Django F() expressions
3. **Build Filters**: Constructs QueryFilterCollection with time range and user-provided filters from the provider map
4. **Apply Group By**: Extracts group_by fields from parameters and maps them to database fields
5. **Execute Query**: Chains Django ORM operations (filter → annotate → values → annotate → order_by) and formats the response

### Response Formatting

Query handlers transform Django QuerySet results into API response format:

```python
{
    "meta": {
        "count": 10,
        "filter": {...},
        "group_by": {...},
        "order_by": {...}
    },
    "links": {
        "first": "...",
        "next": "...",
        "previous": "...",
        "last": "..."
    },
    "data": [
        {
            "date": "2025-01",
            "accounts": [
                {
                    "account": "123456789012",
                    "account_alias": "production",
                    "values": [
                        {
                            "date": "2025-01",
                            "cost": {
                                "total": {"value": 1234.56, "units": "USD"},
                                "raw": {"value": 1000.00, "units": "USD"},
                                "markup": {"value": 234.56, "units": "USD"}
                            }
                        }
                    ]
                }
            ]
        }
    ]
}
```

---

## API Views and Endpoints

### View Structure

Views ([`AWSView`](../../koku/api/report/aws/view.py), etc.) inherit from `ReportView` and configure:
- **permission_classes**: Access control (e.g., `AwsAccessPermission`)
- **provider**: Provider constant (e.g., `Provider.PROVIDER_AWS`)
- **serializer**: Query parameter serializer class
- **query_handler**: Query handler class
- **tag_providers**: List of provider types for tag queries
- **report**: Report type string (e.g., "costs", "instance_type", "storage")

### ReportView Base Class

The [`ReportView`](../../koku/api/report/view.py) base class provides common GET request handling:
1. Parse and validate parameters using `QueryParameters` and the configured serializer
2. Create query handler instance with validated parameters
3. Execute query via `handler.execute_query()`
4. Apply pagination to results
5. Return paginated response

### URL Configuration

Views are registered in [`koku/api/urls.py`](../../koku/api/urls.py) using Django's `path()` function. Each endpoint is wrapped with caching middleware (`cache_page()`) for performance, using provider-specific cache prefixes.

### Permissions

Each view specifies permission classes (e.g., `AwsAccessPermission | AWSOUAccessPermission`) that are checked before view execution to control:
- Which providers a user can access
- Which accounts/projects/subscriptions are visible
- Whether specific features are enabled

---

## Data Flow

### Complete Request Flow

Let's trace a sample request through the system:

**Request**: `GET /api/v1/reports/aws/costs/?group_by[account]=*&filter[region]=us-east-1&order_by[cost_total]=desc`

#### Step 1: URL Routing

Django URLs router matches `"reports/aws/costs/"` and routes to `AWSCostView.as_view()`

#### Step 2: View Processing

`AWSCostView` inherits configuration from `AWSView`:
- provider = Provider.PROVIDER_AWS
- report = "costs"
- serializer = AWSQueryParamSerializer
- query_handler = AWSReportQueryHandler

#### Step 3: Parameter Extraction

`QueryParameters` extracts and structures request parameters:
- group_by: {"account": "*"}
- filter: {"region": "us-east-1"}
- order_by: {"cost_total": "desc"}
- report_type: "costs" (from view)
- provider: "AWS" (from view)

#### Step 4: Serializer Validation

`AWSQueryParamSerializer` validates the parameters using nested serializers:
- `AWSFilterSerializer` validates the region filter
- `AWSGroupBySerializer` validates the account group_by
- `AWSOrderBySerializer` validates the cost_total ordering
- Returns validated data or raises validation errors

#### Step 5: Query Handler Initialization

`AWSReportQueryHandler` initializes with validated parameters:
- Creates `AWSProviderMap` instance with provider, report_type, schema, and cost_type
- Determines query table/view from provider map
- Sets up group_by options, annotations, and filters

#### Step 6: Provider Map Lookup

Provider map returns configuration for report_type="costs":
- **Aggregates**: Cost calculations (sum of unblended + markup)
- **Annotations**: Field mappings (account → usage_account_id, date truncation)
- **Filters**: Region filter configuration with "icontains" operation
- **View selection**: Selects `AWSCostSummaryByAccountP` for group_by=(account,)

#### Step 7: Query Building

`handler.execute_query()` builds Django ORM query chain:
1. Filter by date range and region (icontains match)
2. Annotate with date (month truncation), account, currency
3. Group by date and account using `.values()`
4. Aggregate costs (total, raw, markup)
5. Order by cost_total descending

#### Step 8: Query Execution

Django ORM translates to SQL:
- SELECT with DATE_TRUNC, SUM aggregations
- FROM appropriate summary table
- WHERE clauses for date range and region (ILIKE)
- GROUP BY date and account
- ORDER BY cost_total DESC

#### Step 9: Response Formatting

`handler._format_query_response()` transforms QuerySet into nested API response structure with date-based grouping, account arrays, and cost breakdowns (total, raw, markup) with units.

#### Step 10: Pagination and Response

`ReportView` applies pagination using `get_paginator()`, paginates the queryset, and returns HTTP response with pagination links (first, next, previous, last).

---

## Provider-Specific Implementations

### AWS Provider

**Files**:
- `koku/api/report/aws/view.py` - View classes
- `koku/api/report/aws/serializers.py` - Serializers
- `koku/api/report/aws/query_handler.py` - Query handler
- `koku/api/report/aws/provider_map.py` - Provider map

**Unique Features**:
- AWS Categories (cost allocation tags)
- Organizational Units (OU) hierarchy
- Multiple cost types (unblended, amortized, blended, net-amortized)
- EC2 compute-specific endpoint

**Key Endpoints**:
- `/api/v1/reports/aws/costs/`
- `/api/v1/reports/aws/instance-types/`
- `/api/v1/reports/aws/storage/`
- `/api/v1/reports/aws/ec2-compute/`
- `/api/v1/tags/aws/`
- `/api/v1/organizations/aws/`

### Azure Provider

**Files**:
- `koku/api/report/azure/view.py`
- `koku/api/report/azure/serializers.py`
- `koku/api/report/azure/query_handler.py`
- `koku/api/report/azure/provider_map.py`

**Unique Features**:
- Subscription-based hierarchy
- Service names differ from AWS

**Key Endpoints**:
- `/api/v1/reports/azure/costs/`
- `/api/v1/reports/azure/instance-types/`
- `/api/v1/reports/azure/storage/`
- `/api/v1/tags/azure/`

### GCP Provider

**Files**:
- `koku/api/report/gcp/view.py`
- `koku/api/report/gcp/serializers.py`
- `koku/api/report/gcp/query_handler.py`
- `koku/api/report/gcp/provider_map.py`

**Unique Features**:
- Project-based organization
- GCP-specific service names
- Credits and promotions

**Key Endpoints**:
- `/api/v1/reports/gcp/costs/`
- `/api/v1/reports/gcp/instance-types/`
- `/api/v1/reports/gcp/storage/`
- `/api/v1/tags/gcp/`

### OpenShift (OCP) Provider

**Files**:
- `koku/api/report/ocp/view.py`
- `koku/api/report/ocp/serializers.py`
- `koku/api/report/ocp/query_handler.py`
- `koku/api/report/ocp/provider_map.py`

**Unique Features**:
- Infrastructure and supplementary costs
- Resource types (CPU, memory, storage, network)
- Node, pod, project, cluster groupings
- Cost models and rate calculations
- Distributed costs

**Key Endpoints**:
- `/api/v1/reports/openshift/costs/`
- `/api/v1/reports/openshift/cpu/`
- `/api/v1/reports/openshift/memory/`
- `/api/v1/reports/openshift/volume/`
- `/api/v1/reports/openshift/network/`
- `/api/v1/reports/openshift/infrastructures/all/`
- `/api/v1/reports/openshift/infrastructures/aws/`
- `/api/v1/reports/openshift/infrastructures/azure/`
- `/api/v1/reports/openshift/infrastructures/gcp/`

### OpenShift on Cloud

**Files**:
- `koku/api/report/aws/openshift/` - OCP on AWS
- `koku/api/report/azure/openshift/` - OCP on Azure
- `koku/api/report/gcp/openshift/` - OCP on GCP
- `koku/api/report/all/openshift/` - OCP on All

**Unique Features**:
- Correlates OCP usage with cloud infrastructure costs
- Allocates cloud costs to OpenShift projects/pods
- Combines infrastructure and OCP cost models

---

## Adding New Endpoints

### Step 1: Define the Data Model

Ensure your database models are in place in [`reporting/provider/aws/models.py`](../../koku/reporting/provider/aws/models.py) with required fields (usage_start, account fields, custom metrics, cost fields).

### Step 2: Create Serializers

Create filter, group_by, and query parameter serializers in [`serializers.py`](../../koku/api/report/aws/serializers.py):
- Extend `BaseFilterSerializer` and `GroupSerializer` for your custom fields
- Set `_opfields` tuple for operator support
- Create top-level serializer extending `AWSQueryParamSerializer`
- Reference your filter and group_by serializers

### Step 3: Update Provider Map

Update [`provider_map.py`](../../koku/api/report/aws/provider_map.py) to add new report type configuration:
- Add report type key to `report_type` dictionary
- Define aggregates (Sum, Max, etc. for your metrics)
- Define annotations (field mappings)
- Specify sum_columns and default_ordering
- Add view selection mapping in `self.views`

### Step 4: Create Query Handler (if needed)

Most reports can use the existing `AWSReportQueryHandler`. Create a custom one in [`query_handler.py`](../../koku/api/report/aws/query_handler.py) only if you need special logic.

### Step 5: Create View

Create view class in [`view.py`](../../koku/api/report/aws/view.py):
- Extend `AWSView` (or appropriate provider base)
- Set `report` attribute to your report type string
- Optionally override `serializer` and `query_handler` if custom

### Step 6: Register URL

Add URL pattern to [`koku/api/urls.py`](../../koku/api/urls.py) using Django's `path()` function, wrapping the view with `cache_page()` for caching.

### Step 7: Add Tests

Create test class in [`koku/api/report/test/aws/test_views.py`](../../koku/api/report/test/aws/test_views.py):
- Extend `IamTestCase` for authentication setup
- Test default query (no parameters)
- Test with group_by, filters, ordering
- Verify response structure and status codes
- Test error cases and edge conditions

### Step 8: Update OpenAPI Spec

The OpenAPI spec must be **manually updated** when adding new endpoints. The spec is located at `docs/specs/openapi.json`.

Add your new endpoint to the spec:

```json
{
  "paths": {
    "/reports/aws/new-report/": {
      "get": {
        "summary": "Get new report data",
        "description": "Returns aggregated cost and usage data for custom metrics.",
        "operationId": "getAWSNewReport",
        "tags": ["Reports"],
        "parameters": [
          {
            "name": "filter[custom_field]",
            "in": "query",
            "description": "Filter by custom field",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "group_by[custom_field]",
            "in": "query",
            "description": "Group by custom field",
            "required": false,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ReportResponse"
                }
              }
            }
          }
        }
      }
    }
  }
}
```

You should also add helpful docstrings to your view class for developer reference:

```python
class AWSNewReportView(AWSView):
    """
    Get new report data.

    Returns aggregated cost and usage data for custom metrics.

    Query Parameters:
        - filter[custom_field]: Filter by custom field
        - group_by[custom_field]: Group by custom field
        - order_by[cost_total]: Order by total cost
    """
    report = "new_report"
```

---

## Best Practices

### 1. Serializer Design

- **Keep serializers focused**: One serializer per concern (filter, group_by, order_by, exclude)
- **Use inheritance**: Extend base serializers to avoid duplication
- **Validate early**: Catch invalid parameters before query execution
- **Provide clear error messages**: Help users understand what went wrong

### 2. Provider Map Design

- **Keep mappings data-driven**: Avoid logic in provider maps
- **Use views for optimization**: Create database views for common query patterns
- **Document aggregations**: Comment complex Django ORM expressions
- **Test with real data**: Ensure aggregations produce correct results

### 3. Query Handler Design

- **Keep handlers stateless**: All state should be in parameters and mapper
- **Optimize queries**: Use select_related, prefetch_related appropriately
- **Handle edge cases**: Wildcards, empty results, org units
- **Log expensive queries**: Help identify performance issues

### 4. View Design

- **Keep views thin**: Logic belongs in serializers, handlers, and maps
- **Use permissions**: Restrict access appropriately
- **Cache responses**: Use Django's cache framework
- **Handle errors gracefully**: Return appropriate HTTP status codes

---

## Common Patterns

### Pattern 1: Adding a New Filter Field

1. Add field to FilterSerializer
2. Add mapping to provider map filters section
3. Test with API request

### Pattern 2: Adding a New Group By Field

1. Add field to GroupBySerializer
2. Add annotation to provider map
3. Add to group_by_options list
4. Create or select appropriate database view
5. Add view mapping if needed

### Pattern 3: Adding a New Aggregation

1. Define aggregation in provider map aggregates section
2. Add corresponding annotation if needed
3. Add to sum_columns list if it should be summed
4. Test with various group_by combinations

### Pattern 4: Supporting Multiple Providers

1. Create base serializers with common fields
2. Create provider-specific serializers that inherit from base
3. Create base provider map structure
4. Implement provider-specific maps with overrides
5. Share query handler logic where possible

---

## Troubleshooting

### Problem: Serializer Validation Fails

**Check**:
1. Are all required fields present?
2. Are field names correct (check spelling, case)?
3. Are operator prefixes supported for this field?
4. Are cross-field validations passing?

### Problem: Query Returns No Data

**Check**:
1. Are filters too restrictive?
2. Is the date range correct?
3. Is the provider map selecting the right table?
4. Are annotations mapping to correct fields?

### Problem: Query Performance is Slow

**Check**:
1. Are database indexes present for filter fields?
2. Is the appropriate database view selected?
3. Are unnecessary fields being selected?
4. Is pagination being used?

### Problem: Aggregations Return Wrong Values

**Check**:
1. Are F() expressions and Values wrapped correctly?
2. Is Coalesce handling nulls appropriately?
3. Are exchange rates being applied?
4. Is the correct cost_type being used?

---

## Related Documentation

- [Django REST Framework Serializers](https://www.django-rest-framework.org/api-guide/serializers/)
- [Django ORM Aggregation](https://docs.djangoproject.com/en/stable/topics/db/aggregation/)
- [Koku Database Models](../reporting/models/)
- [API Query Parameters](../api/query-params.md)
- [Celery Tasks Architecture](./celery-tasks.md)

---

## Document Version

- **Last Updated**: 2025-10-21
- **Koku Version**: Current
- **Author**: Architecture Documentation
