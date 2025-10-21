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
│                         HTTP Request                                     │
│                    GET /api/v1/reports/aws/costs/                       │
│                    ?group_by[account]=*&filter[region]=us-east-1        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          URL Router                                      │
│                      (koku/api/urls.py)                                 │
│   Routes to: AWSCostView (report/aws/view.py)                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ReportView (Base View)                             │
│                     (report/view.py)                                     │
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
│  - Selects from: AWSCostSummaryP, AWSCostSummaryByAccountP, etc.       │
│  - Applies filters, aggregations, groupings                             │
│  - Returns QuerySet                                                     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Query Handler Processing                             │
│  - Formats data into API response structure                             │
│  - Applies pagination                                                   │
│  - Adds metadata (total, filter, group_by, order_by)                   │
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

Each provider's query parameter serializer composes the four sub-serializers:

```python
class AWSQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for AWS query parameters."""

    GROUP_BY_SERIALIZER = AWSGroupBySerializer
    ORDER_BY_SERIALIZER = AWSOrderBySerializer
    FILTER_SERIALIZER = AWSFilterSerializer
    EXCLUDE_SERIALIZER = AWSExcludeSerializer

    # Provider-specific fields
    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    cost_type = serializers.ChoiceField(choices=AWS_COST_TYPE_CHOICES, required=False)
```

### Key Serializer Features

#### 1. Dynamic Field Support

Serializers support dynamic tag and AWS category fields:

```python
class AWSFilterSerializer(BaseFilterSerializer):
    _opfields = ("account", "service", "region", "az", "product_family", "org_unit_id")
    _aws_category = True  # Enable AWS category dynamic fields

    # Static fields
    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)

    # Dynamic fields are added at runtime:
    # - tag:app
    # - tag:environment
    # - aws_category:project
```

#### 2. Operator Prefixes

Serializers support operator prefixes for advanced filtering:

```python
_opfields = ("account", "service", "region")

# Generates fields:
# - account, and:account, or:account, exact:account
# - service, and:service, or:service, exact:service
# - region, and:region, or:region, exact:region
```

Example API usage:
```
?filter[and:account]=123456&filter[and:account]=789012  # Intersection
?filter[or:account]=123456&filter[or:account]=789012   # Union
?filter[exact:account]=123456                           # Exact match (no partial)
```

#### 3. Validation Logic

**Common Validations** (in `BaseSerializer` and `ParamSerializer`):
- Unknown fields are rejected
- start_date must be before end_date
- start_date and end_date cannot be used with time_scope_value/time_scope_units
- order_by requires matching group_by (in most cases)

**Provider-Specific Validations** (in provider serializers):
```python
# AWS example
def validate_group_by(self, value):
    """Validate AWS-specific group_by rules."""
    # Org unit validation
    group_by_params = self.initial_data.get("group_by", {})
    org_unit_group_keys = ["org_unit_id", "or:org_unit_id"]

    # Cannot mix org_unit_id and or:org_unit_id
    # Only valid for costs endpoint
    # Cannot use wildcard with org_unit_id
```

---

## Provider Maps

### Provider Map Structure

A provider map is a data structure that defines how API parameters map to database operations.

```python
class AWSProviderMap(ProviderMap):
    def __init__(self, provider, report_type, schema_name, cost_type, markup_cost="markup_cost"):
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AWS,
                "alias": "account_alias__account_alias",
                "annotations": {
                    "account": "usage_account_id",      # API param -> DB field
                    "service": "product_code",
                    "az": "availability_zone",
                },
                "filters": {
                    "account": [
                        {"field": "account_alias__account_alias", "operation": "icontains"},
                        {"field": "usage_account_id", "operation": "icontains"},
                    ],
                    "service": {"field": "product_code", "operation": "icontains"},
                },
                "group_by_options": ["service", "account", "region", "az"],
                "tag_column": "tags",
                "aws_category_column": "cost_category",
                "report_type": {
                    "costs": {...},
                    "instance_type": {...},
                    "storage": {...},
                },
                "tables": {"query": AWSCostEntryLineItemDailySummary},
            }
        ]
```

### Report Type Configurations

Each report type within a provider map has its own configuration:

```python
"report_type": {
    "costs": {
        "aggregates": {
            # Django aggregation functions
            "cost_total": Sum(F("unblended_cost") + F("markup_cost")),
            "cost_raw": Sum("unblended_cost"),
            "cost_markup": Sum("markup_cost"),
        },
        "annotations": {
            # Per-row annotations
            "cost_units": Coalesce("currency_code", Value("USD")),
            "account": F("usage_account_id"),
        },
        "filter": [
            # Static filters for this report type
        ],
        "cost_units_key": "currency_code",
        "cost_units_fallback": "USD",
        "sum_columns": ["cost_total", "infra_total", "sup_total"],
        "default_ordering": {"cost_total": "desc"},
    }
}
```

### View Selection

Provider maps include a `views` dictionary that selects optimized database views based on group_by parameters:

```python
self.views = {
    "costs": {
        "default": AWSCostSummaryP,                           # No group_by
        ("account",): AWSCostSummaryByAccountP,              # group_by[account]
        ("region",): AWSCostSummaryByRegionP,                # group_by[region]
        ("account", "region"): AWSCostSummaryByRegionP,      # group_by[account][region]
        ("service",): AWSCostSummaryByServiceP,              # group_by[service]
    }
}
```

**How it works**:
1. Query handler determines which parameters are in group_by
2. Creates a tuple of sorted group_by keys: `("account", "service")`
3. Looks up that tuple in the views dictionary
4. Uses the corresponding database view for optimal performance

### Filter Composition

Provider maps support complex filter definitions:

```python
"filters": {
    "account": [
        {
            "field": "account_alias__account_alias",
            "operation": "icontains",
            "composition_key": "account_filter"
        },
        {
            "field": "usage_account_id",
            "operation": "icontains",
            "composition_key": "account_filter"
        },
    ]
}
```

This creates an **OR** filter: `(account_alias__icontains=X) | (usage_account_id__icontains=X)`

### Aggregations and Annotations

**Aggregates**: Applied to the entire queryset (GROUP BY level)
```python
"aggregates": {
    "cost_total": Sum(F("unblended_cost") + F("markup_cost")),
    "usage": Sum("usage_amount"),
}
```

**Annotations**: Applied per-row before grouping
```python
"annotations": {
    "cost_units": Coalesce("currency_code", Value("USD")),
    "date": TruncDay("usage_start"),
}
```

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

```python
class AWSReportQueryHandler(ReportQueryHandler):
    provider = Provider.PROVIDER_AWS

    def __init__(self, parameters):
        # Initialize provider map
        kwargs = {
            "provider": self.provider,
            "report_type": parameters.report_type,
            "schema_name": parameters.tenant.schema_name,
            "cost_type": parameters.cost_type,
        }
        self._mapper = AWSProviderMap(**kwargs)

        # Set group_by options from provider map
        self.group_by_options = self._mapper.provider_map.get("group_by_options")

        # Call parent
        super().__init__(parameters)
```

### Query Building Process

1. **Determine Query Table**
   ```python
   query_table = self._mapper.query_table  # From provider map
   ```

2. **Build Annotations**
   ```python
   @property
   def annotations(self):
       annotations = {
           "date": self.date_trunc("usage_start"),
           "currency_annotation": Value(self.currency),
       }
       # Add group_by fields
       for param in group_by_params:
           if db_field := fields.get(param):
               annotations[param] = F(db_field)
       # Add tag annotations
       for tag_db_name, _, original_tag in self._tag_group_by:
           annotations[tag_db_name] = KT(f"{self._mapper.tag_column}__{original_tag}")
       return annotations
   ```

3. **Build Filters**
   ```python
   def _get_filter(self, delta=False):
       filters = QueryFilterCollection()

       # Time range filters
       filters.add(field="usage_start__gte", value=start_date)
       filters.add(field="usage_start__lte", value=end_date)

       # User-provided filters
       for key, value in self.parameters.get("filter", {}).items():
           filter_config = self._mapper.filters.get(key)
           filters.add(field=filter_config["field"],
                      operation=filter_config["operation"],
                      value=value)

       return filters
   ```

4. **Apply Group By**
   ```python
   def _get_group_by(self):
       group_by = []
       for param in self.parameters.get("group_by", {}).keys():
           if db_field := self._mapper.annotations.get(param):
               group_by.append(db_field)
       return group_by
   ```

5. **Execute Query**
   ```python
   def execute_query(self):
       query = self.query_table.objects.filter(
           self._get_filter()
       ).annotate(
           **self.annotations
       ).values(
           *self._get_group_by()
       ).annotate(
           **self._mapper.aggregates
       ).order_by(
           self.order
       )

       return self._format_query_response(query)
   ```

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

```python
class AWSView(ReportView):
    """AWS Base View."""
    permission_classes = [AwsAccessPermission | AWSOUAccessPermission]
    provider = Provider.PROVIDER_AWS
    serializer = AWSQueryParamSerializer
    query_handler = AWSReportQueryHandler
    tag_providers = [Provider.PROVIDER_AWS]


class AWSCostView(AWSView):
    """Get cost data."""
    report = "costs"


class AWSInstanceTypeView(AWSView):
    """Get instance type data."""
    report = "instance_type"


class AWSStorageView(AWSView):
    """Get storage data."""
    report = "storage"
```

### ReportView Base Class

The `ReportView` base class provides common functionality:

```python
class ReportView(APIView):
    def get(self, request, **kwargs):
        # 1. Parse and validate parameters
        params = QueryParameters(request=request, caller=self, **kwargs)

        # 2. Create query handler
        handler = self.query_handler(params)

        # 3. Execute query
        output = handler.execute_query()

        # 4. Apply pagination
        paginator = get_paginator(params, handler.max_rank)
        paginated_result = paginator.paginate_queryset(output, request)

        # 5. Return response
        return paginator.get_paginated_response(paginated_result)
```

### URL Configuration

Views are registered in `koku/api/urls.py`:

```python
urlpatterns = [
    path(
        "reports/aws/costs/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS,
                  cache=CacheEnum.api,
                  key_prefix=AWS_CACHE_PREFIX)(
            AWSCostView.as_view()
        ),
        name="reports-aws-costs",
    ),
    path(
        "reports/aws/instance-types/",
        cache_page(timeout=settings.CACHE_MIDDLEWARE_SECONDS,
                  cache=CacheEnum.api,
                  key_prefix=AWS_CACHE_PREFIX)(
            AWSInstanceTypeView.as_view()
        ),
        name="reports-aws-instance-type",
    ),
]
```

### Permissions

Each view specifies permission classes:

```python
permission_classes = [AwsAccessPermission | AWSOUAccessPermission]
```

Permissions are checked before view execution and control:
- Which providers a user can access
- Which accounts/projects/subscriptions are visible
- Whether specific features are enabled

---

## Data Flow

### Complete Request Flow

Let's trace a sample request through the system:

**Request**: `GET /api/v1/reports/aws/costs/?group_by[account]=*&filter[region]=us-east-1&order_by[cost_total]=desc`

#### Step 1: URL Routing

```python
# urls.py matches: "reports/aws/costs/"
# Calls: AWSCostView.as_view()
```

#### Step 2: View Processing

```python
# AWSCostView inherits from AWSView:
# - provider = Provider.PROVIDER_AWS
# - report = "costs"
# - serializer = AWSQueryParamSerializer
# - query_handler = AWSReportQueryHandler
```

#### Step 3: Parameter Extraction

```python
# QueryParameters extracts:
params = {
    "group_by": {"account": "*"},
    "filter": {"region": "us-east-1"},
    "order_by": {"cost_total": "desc"},
    "report_type": "costs",  # from view
    "provider": "AWS",       # from view
}
```

#### Step 4: Serializer Validation

```python
# AWSQueryParamSerializer validates:
serializer = AWSQueryParamSerializer(data=params)
serializer.is_valid(raise_exception=True)

# Validates via:
# - AWSFilterSerializer (region field)
# - AWSGroupBySerializer (account field)
# - AWSOrderBySerializer (cost_total field)

# Returns validated data
```

#### Step 5: Query Handler Initialization

```python
handler = AWSReportQueryHandler(params)

# Initializes:
# - AWSProviderMap(provider="AWS", report_type="costs", ...)
# - Determines query_table from provider map
# - Sets up group_by_options, annotations, filters
```

#### Step 6: Provider Map Lookup

```python
# Provider map returns for report_type="costs":
{
    "aggregates": {
        "cost_total": Sum(F("unblended_cost") + F("markup_cost")),
        ...
    },
    "annotations": {
        "account": F("usage_account_id"),
        "date": TruncMonth("usage_start"),
        ...
    },
    "filters": {
        "region": {"field": "region", "operation": "icontains"},
    },
    "sum_columns": ["cost_total"],
    "default_ordering": {"cost_total": "desc"},
}

# View selection for group_by=(account,):
query_table = AWSCostSummaryByAccountP
```

#### Step 7: Query Building

```python
# handler.execute_query() builds:
query = AWSCostSummaryByAccountP.objects.filter(
    usage_start__gte=start_date,
    usage_start__lte=end_date,
    region__icontains="us-east-1"
).annotate(
    date=TruncMonth("usage_start"),
    account=F("usage_account_id"),
    currency_annotation=Value("USD")
).values(
    "date",
    "account"
).annotate(
    cost_total=Sum(F("unblended_cost") + F("markup_cost")),
    cost_raw=Sum("unblended_cost"),
    cost_markup=Sum("markup_cost")
).order_by(
    "-cost_total"
)
```

#### Step 8: Query Execution

```python
# Django ORM executes SQL:
SELECT
    DATE_TRUNC('month', usage_start) AS date,
    usage_account_id AS account,
    SUM(unblended_cost + markup_cost) AS cost_total,
    SUM(unblended_cost) AS cost_raw,
    SUM(markup_cost) AS cost_markup
FROM reporting_awscostsummarybyaccountp
WHERE usage_start >= '2025-01-01'
  AND usage_start <= '2025-01-31'
  AND region ILIKE '%us-east-1%'
GROUP BY DATE_TRUNC('month', usage_start), usage_account_id
ORDER BY cost_total DESC;
```

#### Step 9: Response Formatting

```python
# handler._format_query_response() transforms QuerySet to:
{
    "data": [
        {
            "date": "2025-01",
            "accounts": [
                {
                    "account": "123456789012",
                    "values": [{
                        "date": "2025-01",
                        "cost": {
                            "total": {"value": 5000.00, "units": "USD"},
                            "raw": {"value": 4000.00, "units": "USD"},
                            "markup": {"value": 1000.00, "units": "USD"}
                        }
                    }]
                }
            ]
        }
    ],
    "meta": {
        "count": 1,
        "filter": {"region": "us-east-1"},
        "group_by": {"account": "*"},
        "order_by": {"cost_total": "desc"}
    }
}
```

#### Step 10: Pagination and Response

```python
# ReportView applies pagination:
paginator = get_paginator(params, max_rank=1)
paginated_result = paginator.paginate_queryset(output, request)

# Returns HTTP response with pagination links
return paginator.get_paginated_response(paginated_result)
```

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

Ensure your database models are in place:
```python
# reporting/provider/aws/models.py
class AWSNewReportSummary(models.Model):
    usage_start = models.DateField()
    usage_account_id = models.CharField()
    custom_field = models.DecimalField()
    cost = models.DecimalField()
    # ... other fields
```

### Step 2: Create Serializers

```python
# koku/api/report/aws/serializers.py

class AWSNewReportFilterSerializer(BaseFilterSerializer):
    """Filter serializer for new report."""
    _opfields = ("custom_field",)
    custom_field = StringOrListField(child=serializers.CharField(), required=False)


class AWSNewReportGroupBySerializer(GroupSerializer):
    """Group by serializer for new report."""
    _opfields = ("custom_field",)
    custom_field = StringOrListField(child=serializers.CharField(), required=False)


class AWSNewReportQueryParamSerializer(AWSQueryParamSerializer):
    """Query parameter serializer for new report."""
    FILTER_SERIALIZER = AWSNewReportFilterSerializer
    GROUP_BY_SERIALIZER = AWSNewReportGroupBySerializer
```

### Step 3: Update Provider Map

```python
# koku/api/report/aws/provider_map.py

class AWSProviderMap(ProviderMap):
    def __init__(self, ...):
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AWS,
                "report_type": {
                    # ... existing report types ...

                    "new_report": {
                        "aggregates": {
                            "cost_total": Sum("cost"),
                            "custom_total": Sum("custom_field"),
                        },
                        "annotations": {
                            "account": F("usage_account_id"),
                            "custom": F("custom_field"),
                            "cost_units": Value("USD"),
                        },
                        "filter": [],
                        "group_by": [],
                        "cost_units_key": "currency_code",
                        "sum_columns": ["cost_total", "custom_total"],
                        "default_ordering": {"cost_total": "desc"},
                        "tables": {"query": AWSNewReportSummary},
                    },
                },
            }
        ]

        # Add view selection
        self.views = {
            # ... existing views ...
            "new_report": {
                "default": AWSNewReportSummary,
                ("custom_field",): AWSNewReportByCustomFieldSummary,
            },
        }
```

### Step 4: Create Query Handler (if needed)

Most reports can use the existing `AWSReportQueryHandler`. Create a custom one only if you need special logic:

```python
# koku/api/report/aws/query_handler.py

class AWSNewReportQueryHandler(AWSReportQueryHandler):
    """Query handler for new report type."""

    def execute_query(self):
        """Custom query execution if needed."""
        # Add custom logic here
        return super().execute_query()
```

### Step 5: Create View

```python
# koku/api/report/aws/view.py

class AWSNewReportView(AWSView):
    """Get new report data."""
    report = "new_report"
    serializer = AWSNewReportQueryParamSerializer  # if custom
    query_handler = AWSNewReportQueryHandler  # if custom
```

### Step 6: Register URL

```python
# koku/api/urls.py

urlpatterns = [
    # ... existing patterns ...
    path(
        "reports/aws/new-report/",
        cache_page(
            timeout=settings.CACHE_MIDDLEWARE_SECONDS,
            cache=CacheEnum.api,
            key_prefix=AWS_CACHE_PREFIX
        )(AWSNewReportView.as_view()),
        name="reports-aws-new-report",
    ),
]
```

### Step 7: Add Tests

```python
# koku/api/report/test/aws/test_views.py

class AWSNewReportViewTest(IamTestCase):
    """Test AWS new report view."""

    def test_execute_query_default(self):
        """Test default query."""
        url = reverse("reports-aws-new-report")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_with_group_by(self):
        """Test query with group_by."""
        url = reverse("reports-aws-new-report")
        url += "?group_by[custom_field]=*"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
```

### Step 8: Update OpenAPI Spec

The OpenAPI spec is auto-generated from the views and serializers, but you may need to add documentation strings:

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
