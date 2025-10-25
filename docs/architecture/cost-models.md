# Cost Models Architecture

**Purpose:** This document provides a comprehensive overview of Koku's cost model architecture, covering both limited cloud provider capabilities (markup/discount only) and advanced OpenShift features (usage-based rates, tag-based pricing, and cost distribution).

**Last Updated:** October 21, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Cloud Provider Cost Models (Limited)](#cloud-provider-cost-models-limited)
3. [OpenShift Cost Models (Advanced)](#openshift-cost-models-advanced)
4. [Tag-Based Rates (Deep Dive)](#tag-based-rates-deep-dive)
5. [Cost Distribution](#cost-distribution)
6. [Data Model](#data-model)
7. [Code Architecture](#code-architecture)
8. [Cost Calculation Pipeline](#cost-calculation-pipeline)
9. [Examples and Use Cases](#examples-and-use-cases)

---

## Overview

### What Are Cost Models?

Cost models allow users to **associate prices to metrics and usage**, providing fine-tuned control over cloud cost calculations. They serve two fundamentally different purposes:

1. **Cloud Providers (AWS, Azure, GCP):** Apply simple markup/discount percentages
2. **OpenShift (OCP):** Calculate costs from scratch using comprehensive rate structures

Cost models are **essential for OpenShift** because raw OCP data contains **no inherent cost information**—only usage metrics (CPU hours, memory GB, storage). Without a cost model, OpenShift data cannot be assigned any monetary value.

**Important:** For **OCP-on-Cloud** deployments (OpenShift running on AWS/Azure/GCP), costs come from **both sources**:
- **Infrastructure costs** from the correlated cloud provider (e.g., AWS EC2 instances)
- **Supplementary costs** from the cost model (e.g., OpenShift overhead, licensing)

For **OCP-on-Prem** deployments, all costs come from the cost model since there is no cloud provider correlation.

### Key Concepts

| Concept                  | Description                                             | Applies To           |
| ------------------------ | ------------------------------------------------------- | -------------------- |
| **Markup**               | Percentage adjustment to existing costs                 | AWS, Azure, GCP, OCP |
| **Tiered Rates**         | Fixed rates per metric unit (e.g., $0.05/CPU core-hour) | OCP only             |
| **Tag-Based Rates**      | Different rates based on label values                   | OCP only             |
| **Distribution**         | How costs are allocated (CPU vs Memory)                 | OCP only             |
| **Infrastructure Rates** | Rates tied to cloud infrastructure costs                | OCP only             |
| **Supplementary Rates**  | Additional costs beyond infrastructure                  | OCP only             |

---

## Cloud Provider Cost Models (Limited)

### Capabilities

Cloud provider cost models support **only one feature**: applying a **markup or discount percentage** to existing costs.

**Why Limited?**
- AWS, Azure, and GCP **already provide cost data** in their billing reports
- Cost models simply adjust these costs up or down by a percentage
- No need for complex rate structures since costs are provided by the cloud vendor

### Markup Structure

```json
{
  "name": "Cost Management AWS Cost Model",
  "description": "A cost model for markup on AWS costs.",
  "source_type": "AWS",
  "source_uuids": ["PROVIDER_UUID"],
  "rates": [],
  "markup": {
    "value": 10,
    "unit": "percent"
  }
}
```

### How Markup Is Applied

**Implementation:**
- **AWS:** [`koku/masu/database/aws_report_db_accessor.py`](../../koku/masu/database/aws_report_db_accessor.py) - `populate_markup_cost()` method
- **Azure:** [`koku/masu/database/azure_report_db_accessor.py`](../../koku/masu/database/azure_report_db_accessor.py) - `populate_markup_cost()` method
- **GCP:** [`koku/masu/database/gcp_report_db_accessor.py`](../../koku/masu/database/gcp_report_db_accessor.py) - `populate_markup_cost()` method

**Key Points:**
- Markup is a decimal (e.g., `0.10` for 10%)
- Applied to **all cost types**: unblended, blended, savings plan, amortized (AWS); pretax_cost (Azure/GCP)
- Stored in separate `markup_cost*` columns in the database
- Uses Django ORM `F()` expressions for database-level calculations: `markup_cost = F("cost_field") * markup`

### Database Impact

**Tables Updated:**
- `reporting_awscostentrylineitem_daily_summary`
- `reporting_azurecostentrylineitem_daily_summary`
- `reporting_gcpcostentrylineitem_daily_summary`
- OCP-on-Cloud perspectives (e.g., `reporting_ocpawscostlineitem_project_daily_summary_p`)

**SQL Example:**
```sql
-- Apply 10% markup to AWS costs
UPDATE reporting_awscostentrylineitem_daily_summary
SET
    markup_cost = unblended_cost * 0.10,
    markup_cost_blended = blended_cost * 0.10,
    markup_cost_amortized = calculated_amortized_cost * 0.10
WHERE
    cost_entry_bill_id = 12345
    AND usage_start >= '2025-01-01'
    AND usage_start < '2025-02-01';
```

---

## OpenShift Cost Models (Advanced)

### Why OpenShift Needs Cost Models

Unlike cloud providers, OpenShift reports contain **only usage metrics**:
- CPU core hours
- Memory gigabyte hours
- Storage gigabyte months
- No cost data

**Cost models transform usage → cost** by applying rates to these metrics.

### OpenShift Cost Sources

OpenShift costs can come from **two sources** depending on the deployment model:

| Deployment Model                 | Infrastructure Costs           | Supplementary Costs | Total Cost Calculation                                           |
| -------------------------------- | ------------------------------ | ------------------- | ---------------------------------------------------------------- |
| **OCP-on-Cloud** (AWS/Azure/GCP) | From correlated cloud provider | From cost model     | `cloud_infrastructure_cost + cost_model_supplementary_cost`      |
| **OCP-on-Prem**                  | From cost model                | From cost model     | `cost_model_infrastructure_cost + cost_model_supplementary_cost` |

**Key Point:** When an OCP cluster is **correlated with a cloud provider** (e.g., OCP running on AWS EC2 instances), Koku matches the OCP usage to the underlying cloud infrastructure costs. The cost model then adds supplementary costs (OpenShift licensing, management overhead, etc.).

**Example - OCP on AWS:**
```
Infrastructure costs: $1,000 (from AWS - EC2 instances, EBS volumes, etc.)
Cost model supplementary rates: $200 (OpenShift overhead at $0.02/core-hour)
Total OCP cost: $1,200
```

**Example - OCP on-prem:**
```
Infrastructure costs: $800 (from cost model - estimated data center costs)
Cost model supplementary rates: $200 (OpenShift licensing, support)
Total OCP cost: $1,000
```

**How Correlation Works:**
- OCP nodes are matched to cloud resources using tags, resource IDs, or instance metadata
- Cloud costs are allocated to OCP namespaces based on usage ratios
- Cost models add supplementary costs on top of allocated infrastructure costs
- See [OCP CSV Processing Architecture](./csv-processing-ocp.md) for details on infrastructure matching

### Cost Model Structure

OpenShift cost models consist of **three main components**:

1. **Tiered Rates** (Usage-based)
2. **Monthly Rates** (Subscription-based)
3. **Tag-Based Rates** (Label-driven)

### 1. Tiered Rates (Usage-Based)

**Purpose:** Assign costs per unit of usage.

**Supported Metrics:**

| Metric                               | Unit | Description         | Formula                     |
| ------------------------------------ | ---- | ------------------- | --------------------------- |
| `cpu_core_usage_per_hour`            | USD  | Actual CPU usage    | `usage_hours * rate`        |
| `cpu_core_request_per_hour`          | USD  | Requested CPU       | `request_hours * rate`      |
| `cpu_core_effective_usage_per_hour`  | USD  | Max(usage, request) | `effective_hours * rate`    |
| `memory_gb_usage_per_hour`           | USD  | Actual memory usage | `usage_gb_hours * rate`     |
| `memory_gb_request_per_hour`         | USD  | Requested memory    | `request_gb_hours * rate`   |
| `memory_gb_effective_usage_per_hour` | USD  | Max(usage, request) | `effective_gb_hours * rate` |
| `storage_gb_usage_per_month`         | USD  | Actual PVC usage    | `usage_gb_months * rate`    |
| `storage_gb_request_per_month`       | USD  | Requested PVC       | `request_gb_months * rate`  |
| `node_core_cost_per_hour`            | USD  | Node core usage     | `core_hours * rate`         |
| `cluster_core_cost_per_hour`         | USD  | Cluster core usage  | `core_hours * rate`         |

**JSON Example:**
```json
{
  "metric": {
    "name": "cpu_core_usage_per_hour"
  },
  "tiered_rates": [
    {
      "unit": "USD",
      "value": 0.007,
      "usage_start": null,
      "usage_end": null
    }
  ],
  "cost_type": "Supplementary"
}
```

**SQL Implementation:**

See [`koku/masu/database/sql/openshift/cost_model/usage_costs.sql`](../../koku/masu/database/sql/openshift/cost_model/usage_costs.sql) for the complete SQL implementation.

**How it works:**
- Multiplies usage metrics (pod_usage_cpu_core_hours, pod_request_cpu_core_hours, etc.) by their corresponding rates
- Aggregates costs across CPU, memory, and volume dimensions
- Stores results in `cost_model_cpu_cost`, `cost_model_memory_cost`, `cost_model_volume_cost` columns

### 2. Monthly Rates (Subscription-Based)

**Purpose:** Flat monthly costs distributed across usage (e.g., subscription fees, licensing).

**Supported Metrics:**

| Metric                     | Description                        | Amortization | Formula                                                               |
| -------------------------- | ---------------------------------- | ------------ | --------------------------------------------------------------------- |
| `node_cost_per_month`      | Fixed cost per node per month      | Yes          | `(effective_usage / capacity) * monthly_rate / days_in_month`         |
| `node_core_cost_per_month` | Cost per node core per month       | Yes          | `(effective_usage / capacity) * cores * monthly_rate / days_in_month` |
| `cluster_cost_per_month`   | Fixed cost per cluster per month   | Yes          | `(effective_usage / capacity) * monthly_rate / days_in_month`         |
| `pvc_cost_per_month`       | Fixed cost per PVC per month       | Yes          | `monthly_rate / pvc_count / days_in_month`                            |
| `vm_cost_per_month`        | Cost per virtual machine per month | Yes          | `monthly_rate / days_in_month`                                        |

**Amortization:** Monthly costs are **divided by days in the month** to create daily rates.

**JSON Example:**
```json
{
  "metric": {
    "name": "node_cost_per_month"
  },
  "tiered_rates": [
    {
      "unit": "USD",
      "value": 1000,
      "usage_start": null,
      "usage_end": null
    }
  ],
  "cost_type": "Infrastructure"
}
```

**SQL Implementation:**

See [`koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql`](../../koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql) for the complete implementation.

**How it works:**
- Calculates daily amortized costs from monthly rates
- Distributes costs based on usage ratio (effective_usage / capacity)
- Handles different monthly cost types: Cluster, Node, Node_Core_Month
- Respects distribution setting (CPU vs Memory)

**Database Queries by Monthly Cost Type:**

```sql
-- Node monthly costs
SELECT * FROM reporting_ocpusagelineitem_daily_summary
WHERE monthly_cost_type = 'Node';

-- Cluster monthly costs
SELECT * FROM reporting_ocpusagelineitem_daily_summary
WHERE monthly_cost_type = 'Cluster';

-- Node core monthly costs
SELECT * FROM reporting_ocpusagelineitem_daily_summary
WHERE monthly_cost_type = 'Node_Core_Month';

-- PVC monthly costs
SELECT * FROM reporting_ocpusagelineitem_daily_summary
WHERE monthly_cost_type = 'PVC';
```

### 3. Infrastructure vs Supplementary Rates

Cost models distinguish between two **cost types**:

| Cost Type          | Purpose                                                                        | Example Rates                                              |
| ------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| **Infrastructure** | Costs tied to underlying cloud infrastructure (when OCP runs on AWS/Azure/GCP) | CPU, memory, storage rates that match cloud provider costs |
| **Supplementary**  | Additional costs beyond infrastructure (on-prem, licensing, support)           | Cluster subscription, node management fees                 |

**Why This Matters:**
- **OCP-on-Cloud:**
  - Infrastructure costs come **from the correlated cloud provider** (AWS EC2, Azure VMs, GCP Compute)
  - Cost model "Infrastructure" rates are typically **not used** (cloud provides real costs)
  - Cost model "Supplementary" rates add OpenShift overhead on top of cloud costs
- **OCP-on-Prem:**
  - No cloud provider correlation, so **all costs come from the cost model**
  - "Infrastructure" rates represent estimated data center costs (power, cooling, hardware)
  - "Supplementary" rates represent OpenShift licensing, support, management overhead

**JSON Example:**
```json
[
  {
    "metric": {"name": "cpu_core_usage_per_hour"},
    "tiered_rates": [{"unit": "USD", "value": 0.05}],
    "cost_type": "Infrastructure"  // Maps to cloud costs
  },
  {
    "metric": {"name": "cpu_core_usage_per_hour"},
    "tiered_rates": [{"unit": "USD", "value": 0.02}],
    "cost_type": "Supplementary"  // Additional overhead
  }
]
```

---

## Tag-Based Rates (Deep Dive)

### Purpose

Tag-based rates allow **different costs based on pod or PVC labels**. This enables:
- Different rates for production vs development environments
- Team-specific pricing
- Application-tier pricing (frontend vs backend)
- Storage class tiers (gold/silver/bronze)

### How Tag-Based Rates Work

**Concept:** Apply different rates to resources based on their Kubernetes labels.

**Example Scenario:**
```yaml
# Pod with environment label
metadata:
  labels:
    env: prod
    team: platform
```

**Rate Definition:**
```json
{
  "metric": {"name": "node_cost_per_month"},
  "tag_rates": {
    "tag_key": "env",
    "tag_values": [
      {"tag_value": "prod", "value": 500, "default": false},
      {"tag_value": "dev", "value": 200, "default": false},
      {"tag_value": "staging", "value": 300, "default": true}
    ]
  },
  "cost_type": "Supplementary"
}
```

**Result:**
- Pods with `env: prod` → $500/month node cost
- Pods with `env: dev` → $200/month node cost
- Pods with `env: staging` or any other value → $300/month (default)

### Tag-Based Rate Structure

**Full JSON Example:**
```json
{
  "metric": {"name": "cpu_core_effective_usage_per_hour"},
  "tag_rates": {
    "tag_key": "application",
    "tag_values": [
      {
        "unit": "USD",
        "value": 0.05,
        "default": false,
        "tag_value": "OpenCart",
        "description": "E-commerce application"
      },
      {
        "unit": "USD",
        "value": 0.10,
        "default": false,
        "tag_value": "Phoenix",
        "description": "Real-time processing"
      },
      {
        "unit": "USD",
        "value": 0.25,
        "default": true,
        "tag_value": "default",
        "description": "Default rate for unlabeled resources"
      }
    ]
  },
  "cost_type": "Infrastructure"
}
```

**Key Fields:**
- `tag_key`: The label key to match (e.g., `env`, `team`, `app`)
- `tag_value`: The label value to match (e.g., `prod`, `dev`)
- `default`: If `true`, this rate applies when the label exists but has an unknown value
- `value`: The rate to apply

### Default Rates

Tag-based rates support **two default mechanisms**:

1. **Tag-Specific Default:** Applied when the tag key exists but the value doesn't match any defined rates
2. **Global Fallback:** If no tag-based rate is defined, use regular tiered rates

**Example:**
```json
{
  "tag_key": "env",
  "tag_values": [
    {"tag_value": "prod", "value": 0.10, "default": false},
    {"tag_value": "dev", "value": 0.05, "default": false},
    {"tag_value": "default_rate", "value": 0.07, "default": true}
  ]
}
```

**Behavior:**
- `env: prod` → $0.10
- `env: dev` → $0.05
- `env: qa` → $0.07 (default rate, since `qa` is not defined)
- No `env` label → Falls back to tiered rate

### Code Implementation: SQL CASE Generation

**Implementation:** See [`koku/masu/processor/ocp/ocp_cost_model_cost_updater.py`](../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py)

**Key Methods:**
- `_build_node_tag_cost_case_statements()` - Generates CASE statements for pod label-based node costs
- `_build_volume_tag_cost_case_statements()` - Generates CASE statements for volume label-based PVC costs
- `_build_labels_case_statement()` - Normalizes labels for tag-based filtering

**How it works:**
- Dynamically generates SQL CASE statements from rate definitions
- Matches pod/volume labels against tag_key and tag_value
- Applies appropriate rate based on label match
- Handles default rates for unmatched values
- Respects distribution setting (CPU vs Memory)

### Generated SQL Example

The cost updater dynamically generates SQL CASE statements and injects them into templates. See the SQL implementation in:
- [`koku/masu/database/sql/openshift/cost_model/node_cost_by_tag.sql`](../../koku/masu/database/sql/openshift/cost_model/node_cost_by_tag.sql)

**Example:** For tag-based rate `{"env": {"prod": 0.10, "dev": 0.05, "default_value": 0.03}}`, the generated SQL matches pod_labels->>'env' against 'prod', 'dev', or applies the default rate.

### Tag-Based Rates for Storage (PVC)

**Purpose:** Apply different rates to Persistent Volume Claims based on storage class.

**JSON Example:**
```json
{
  "metric": {"name": "pvc_cost_per_month"},
  "tag_rates": {
    "tag_key": "storageclass",
    "tag_values": [
      {"unit": "USD", "value": 93, "tag_value": "gold", "default": false},
      {"unit": "USD", "value": 62, "tag_value": "silver", "default": false},
      {"unit": "USD", "value": 31, "tag_value": "bronze", "default": true}
    ]
  },
  "cost_type": "Infrastructure"
}
```

**SQL Implementation:**

See [`koku/masu/database/sql/openshift/cost_model/monthly_cost_persistentvolumeclaim_by_tag.sql`](../../koku/masu/database/sql/openshift/cost_model/monthly_cost_persistentvolumeclaim_by_tag.sql) for the complete implementation.

**How it works:**
- Matches volume_labels against storage class tag values
- Divides monthly rate by PVC count for fair distribution
- Applies amortization to convert monthly costs to daily costs
- Handles default rates for unmatched storage classes

### Unallocated Costs for Tag-Based Rates

**Concept:** When applying tag-based monthly rates, **unallocated node capacity** must also be costed.

**Unallocated Capacity:**
```
unallocated = node_capacity - pod_effective_usage
```

**Implementation:** See [`koku/masu/database/sql/openshift/cost_model/node_cost_by_tag.sql`](../../koku/masu/database/sql/openshift/cost_model/node_cost_by_tag.sql)

The SQL creates separate records for unallocated capacity, assigning costs to synthetic namespaces based on node role:
- Worker nodes → "Worker unallocated" namespace
- Master/Infra nodes → "Platform unallocated" namespace

---

## Cost Distribution

### Overview

**Cost distribution** reallocates costs from **unallocated or platform resources** to **user projects** based on their usage. This ensures the full cost of the cluster is attributed to the applications consuming resources.

### Distribution Types

Cost models support **two distribution strategies**:

| Distribution Type              | Basis                                | Formula                                                          |
| ------------------------------ | ------------------------------------ | ---------------------------------------------------------------- |
| **CPU Distribution** (default) | Allocate based on CPU usage ratio    | `(project_cpu_usage / total_cpu_usage) * unallocated_cost`       |
| **Memory Distribution**        | Allocate based on memory usage ratio | `(project_memory_usage / total_memory_usage) * unallocated_cost` |

**Configured in Cost Model:**
```json
{
  "distribution": "cpu",  // or "memory"
  "distribution_info": {
    "distribution_type": "cpu"
  }
}
```

### What Gets Distributed?

1. **Worker Unallocated Cost** - Unused capacity on worker nodes
2. **Platform Cost** - Control plane nodes (master, infra)
3. **Unattributed Storage Cost** - Storage costs not tied to PVCs
4. **Unattributed Network Cost** - Network costs not tied to pods

### 1. Worker Unallocated Distribution

**Purpose:** Distribute unused worker node capacity to user projects.

**Implementation:** See [`koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_worker_cost.sql`](../../koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_worker_cost.sql)

**Formula (CPU Distribution):**
```
distributed_cost = (project_cpu_usage / total_user_project_cpu_usage) * worker_unallocated_cost
```

**How it works:**
1. Calculate total worker unallocated cost
2. Calculate total usage across all user projects (excluding unallocated/platform)
3. Distribute to each project based on its usage ratio
4. Deduct from "Worker unallocated" namespace to avoid double-counting

**Example Calculation:**
```
Worker unallocated cost: $100
Project A CPU usage: 25 core-hours
Project B CPU usage: 75 core-hours
Total user project CPU: 100 core-hours

Project A distributed cost: (25 / 100) * $100 = $25
Project B distributed cost: (75 / 100) * $100 = $75
Worker unallocated distributed cost: $0 - $100 = -$100  (deduct to avoid double-counting)
```

### 2. Platform Cost Distribution

**Purpose:** Distribute control plane (master/infra node) costs to user projects.

**Implementation:** See [`koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_platform_cost.sql`](../../koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_platform_cost.sql)

**Formula:**
```
distributed_cost = (project_usage / total_non_platform_usage) * platform_cost
```

**How it works:**
1. Calculate total platform cost (master/infra nodes)
2. Calculate total usage across non-platform projects
3. Distribute to each project based on usage ratio
4. Deduct from platform namespaces to avoid double-counting

### 3. Unattributed Storage Distribution

**Purpose:** Distribute storage costs that aren't tied to specific PVCs.

**Implementation:** See [`koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_storage_cost.sql`](../../koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_storage_cost.sql)

### 4. Unattributed Network Distribution

**Purpose:** Distribute network costs that aren't tied to specific pods.

**Implementation:** See [`koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_network_cost.sql`](../../koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_network_cost.sql)

### Distribution in Action

**Before Distribution:**
```
Namespace: Project A
  raw_cost: $50
  distributed_cost: $0
  total_cost: $50

Namespace: Worker unallocated
  raw_cost: $100
  distributed_cost: $0
  total_cost: $100
```

**After Distribution (CPU, Project A uses 25% of cluster CPU):**
```
Namespace: Project A
  raw_cost: $50
  distributed_cost: $25  (25% of $100)
  total_cost: $75

Namespace: Worker unallocated
  raw_cost: $100
  distributed_cost: -$100  (deducted to avoid double-counting)
  total_cost: $0
```

---

## Data Model

### Database Schema

**Table:** `cost_model`

```sql
CREATE TABLE cost_model (
    uuid UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    source_type VARCHAR(50) NOT NULL,  -- 'AWS', 'AZURE', 'GCP', 'OCP'
    created_timestamp TIMESTAMP DEFAULT NOW(),
    updated_timestamp TIMESTAMP DEFAULT NOW(),
    rates JSONB DEFAULT '{}',
    markup JSONB DEFAULT '{}',
    distribution TEXT DEFAULT 'cpu',  -- 'cpu' or 'memory'
    distribution_info JSONB DEFAULT '{}',
    currency TEXT DEFAULT 'USD'
);
```

**Related Tables:**
- `cost_model_map`: Maps providers to cost models (many-to-many)
- `cost_model_audit`: Tracks cost model changes for auditing

### Cost Model Map

**Table:** `cost_model_map`

```sql
CREATE TABLE cost_model_map (
    id SERIAL PRIMARY KEY,
    provider_uuid UUID NOT NULL,
    cost_model_id UUID REFERENCES cost_model(uuid) ON DELETE CASCADE,
    UNIQUE (provider_uuid, cost_model_id)
);
```

**Purpose:** Allows multiple providers to share the same cost model.

### Django Models

See [`koku/cost_models/models.py`](../../koku/cost_models/models.py) for model definitions:

**Key Models:**
- `CostModel` - Stores cost model configuration (rates, markup, distribution)
- `CostModelMap` - Links providers to cost models (many-to-many relationship)
- `CostModelAudit` - Tracks cost model changes for auditing

**Key Fields:**
- `rates` - JSONField containing tiered and tag-based rate definitions
- `markup` - JSONField containing markup percentage and unit
- `distribution` - Text field: "cpu" or "memory"
- `distribution_info` - JSONField with additional distribution configuration

### Rates JSON Structure

**Infrastructure Rates:**
```json
{
  "cpu_core_usage_per_hour": 0.05,
  "memory_gb_usage_per_hour": 0.01,
  "storage_gb_usage_per_month": 0.10
}
```

**Tag-Based Rates:**
```json
{
  "node_cost_per_month": {
    "env": {
      "prod": 500,
      "dev": 200,
      "default_value": 300
    }
  }
}
```

**Stored Structure:**
```json
{
  "rates": [
    {
      "metric": {"name": "cpu_core_usage_per_hour"},
      "tiered_rates": [{"unit": "USD", "value": 0.05}],
      "cost_type": "Infrastructure"
    },
    {
      "metric": {"name": "node_cost_per_month"},
      "tag_rates": {
        "tag_key": "env",
        "tag_values": [
          {"tag_value": "prod", "value": 500, "default": false},
          {"tag_value": "dev", "value": 200, "default": false},
          {"tag_value": "default", "value": 300, "default": true}
        ]
      },
      "cost_type": "Supplementary"
    }
  ]
}
```

---

## Code Architecture

### Key Components

```
koku/
├── cost_models/
│   ├── models.py                      # Django models (CostModel, CostModelMap)
│   ├── serializers.py                 # API serializers for cost models
│   ├── views.py                       # API views for CRUD operations
│   ├── cost_model_manager.py          # Business logic for cost model operations
│   └── sql_parameters.py              # SQL parameter generation for rates
│
├── masu/
│   ├── processor/
│   │   └── ocp/
│   │       └── ocp_cost_model_cost_updater.py  # Cost calculation engine
│   │
│   └── database/
│       ├── cost_model_db_accessor.py           # Cost model data access
│       ├── ocp_report_db_accessor.py           # OCP data access
│       │
│       └── sql/
│           └── openshift/
│               └── cost_model/
│                   ├── usage_costs.sql                    # Tiered rate calculations
│                   ├── monthly_cost_cluster_and_node.sql  # Monthly rate calculations
│                   ├── monthly_cost_persistentvolumeclaim.sql
│                   ├── node_cost_by_tag.sql               # Tag-based node rates
│                   ├── monthly_cost_persistentvolumeclaim_by_tag.sql
│                   ├── infrastructure_tag_rates.sql       # Tag rate queries
│                   ├── supplementary_tag_rates.sql
│                   └── distribute_cost/
│                       ├── distribute_worker_cost.sql
│                       ├── distribute_platform_cost.sql
│                       ├── distribute_unattributed_storage_cost.sql
│                       └── distribute_unattributed_network_cost.sql
│
└── api/
    └── metrics/
        └── constants.py               # Cost model metric definitions
```

### Cost Model Updater

**Implementation:** See [`koku/masu/processor/ocp/ocp_cost_model_cost_updater.py`](../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py)

**Class:** `OCPCostModelCostUpdater`

**Orchestration Flow:**
1. `_update_usage_costs()` - Apply tiered rates (CPU, memory, storage)
2. `_update_monthly_cost()` - Apply monthly rates (node, cluster, PVC)
3. `_update_tag_usage_costs()` - Apply tag-based usage rates
4. `_update_monthly_tag_based_cost()` - Apply tag-based monthly rates
5. `_update_markup_cost()` - Apply markup percentage
6. `_distribute_costs()` - Distribute unallocated and platform costs

**Key Responsibilities:**
- Load cost model configuration from database
- Generate SQL parameters from rate definitions
- Render Jinja2 SQL templates with rate values
- Execute SQL to populate cost columns
- Handle both Infrastructure and Supplementary cost types

### Cost Model DB Accessor

**Implementation:** See [`koku/masu/database/cost_model_db_accessor.py`](../../koku/masu/database/cost_model_db_accessor.py)

**Class:** `CostModelDBAccessor`

**Key Properties:**
- `cost_model` - Returns the CostModel object for a provider
- `infrastructure_rates` - Extracts Infrastructure tiered rates
- `supplementary_rates` - Extracts Supplementary tiered rates
- `tag_infrastructure_rates` - Extracts Infrastructure tag-based rates
- `tag_supplementary_rates` - Extracts Supplementary tag-based rates
- `markup` - Extracts markup percentage (converted to decimal)
- `distribution_info` - Extracts distribution configuration

**Purpose:** Provides a clean interface for reading cost model configuration from the database and parsing the JSON rate structures.

---

## Cost Calculation Pipeline

### Step-by-Step Process

**For OpenShift (OCP-on-Cloud):**

```
1. Data Ingestion
   ↓ (parallel processing)
   ├─> OCP Usage Data (CPU, memory, storage metrics)
   └─> Cloud Provider Cost Data (AWS/Azure/GCP)
   ↓
2. Infrastructure Matching
   └─> Match OCP nodes to cloud resources (EC2 instances, VMs, etc.)
   ↓
3. Daily Summary Creation
   └─> Combine: infrastructure_raw_cost (from cloud) + usage metrics (from OCP)
   ↓
4. Cost Model Application:
   a. Usage Costs (tiered rates) - typically Supplementary
   b. Monthly Costs (node, cluster, PVC) - typically Supplementary
   c. Tag-Based Usage Costs
   d. Tag-Based Monthly Costs
   e. Markup Application
   f. Cost Distribution
   ↓
5. Database Storage
   ├─> infrastructure_raw_cost (from cloud)
   ├─> infrastructure_markup_cost (from cloud cost model markup)
   ├─> cost_model_cpu_cost (from OCP cost model)
   ├─> cost_model_memory_cost (from OCP cost model)
   └─> cost_model_volume_cost (from OCP cost model)
   ↓
6. API Aggregation & Display
   └─> Total = infrastructure costs + cost model costs
```

**For OpenShift (OCP-on-Prem):**

```
1. Data Ingestion (OCP usage data only)
   ↓
2. Daily Summary Creation (usage metrics only, no costs)
   ↓
3. Cost Model Application:
   a. Usage Costs (tiered rates) - Infrastructure + Supplementary
   b. Monthly Costs (node, cluster, PVC) - Infrastructure + Supplementary
   c. Tag-Based Usage Costs
   d. Tag-Based Monthly Costs
   e. Markup Application
   f. Cost Distribution
   ↓
4. Database Storage (cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost)
   ↓
5. API Aggregation & Display
```

**For Cloud Providers:**

```
1. Data Ingestion (with costs from cloud vendor)
   ↓
2. Daily Summary Creation (costs already present)
   ↓
3. Markup Application (if cost model exists)
   ↓
4. Database Storage (markup_cost columns)
   ↓
5. API Aggregation & Display
```

### Celery Task Integration

**Implementation:** See [`koku/masu/processor/tasks.py`](../../koku/masu/processor/tasks.py)

**Task:** `update_summary_tables`

**When Triggered:**
- After data ingestion completes
- When cost models are created or updated
- During manual re-summarization requests

**What It Does:**
- For OCP: Calls `OCPCostModelCostUpdater.update_summary_cost_model_costs()`
- For Cloud Providers: Calls `populate_markup_cost()` if markup is configured
- Processes date ranges in batches for performance

### SQL Template Rendering

Cost model SQL files use **Jinja2 templating** for dynamic rate injection.

**Template Files:** See [`koku/masu/database/sql/openshift/cost_model/`](../../koku/masu/database/sql/openshift/cost_model/)

**How it works:**
1. Cost model rates are loaded from the database (e.g., `cpu_core_usage_per_hour: 0.007`)
2. Jinja2 renders SQL templates, replacing `{{cpu_core_usage_per_hour}}` with `0.007`
3. Rendered SQL is executed to calculate costs
4. Template variables include rates, dates, schema names, and dynamically generated CASE statements

---

## Examples and Use Cases

### Use Case 1: Simple On-Prem OpenShift

**Scenario:** On-premises OpenShift cluster with fixed monthly costs.

**Cost Model:**
```json
{
  "name": "Simple On-Prem",
  "source_type": "OCP",
  "rates": [
    {
      "metric": {"name": "cpu_core_usage_per_hour"},
      "tiered_rates": [{"unit": "USD", "value": 0.05}],
      "cost_type": "Supplementary"
    },
    {
      "metric": {"name": "memory_gb_usage_per_hour"},
      "tiered_rates": [{"unit": "USD", "value": 0.01}],
      "cost_type": "Supplementary"
    },
    {
      "metric": {"name": "cluster_cost_per_month"},
      "tiered_rates": [{"unit": "USD", "value": 10000}],
      "cost_type": "Supplementary"
    }
  ],
  "distribution": "cpu"
}
```

**Result:**
- CPU usage: 100 core-hours × $0.05 = $5.00
- Memory usage: 500 GB-hours × $0.01 = $5.00
- Cluster monthly cost: $10,000 / 30 days = $333.33/day
- **Total daily cost: $343.33**

### Use Case 2: Environment-Based Pricing

**Scenario:** Different rates for production vs development environments.

**Cost Model:**
```json
{
  "name": "Environment Tiered",
  "source_type": "OCP",
  "rates": [
    {
      "metric": {"name": "node_cost_per_month"},
      "tag_rates": {
        "tag_key": "env",
        "tag_values": [
          {"tag_value": "prod", "value": 1000, "default": false},
          {"tag_value": "dev", "value": 300, "default": false},
          {"tag_value": "default", "value": 500, "default": true}
        ]
      },
      "cost_type": "Supplementary"
    }
  ],
  "distribution": "cpu"
}
```

**Result:**
```yaml
# Pod in production
metadata:
  labels:
    env: prod
# Cost: $1000/month node rate

# Pod in development
metadata:
  labels:
    env: dev
# Cost: $300/month node rate

# Pod with no label or unknown value
metadata:
  labels:
    env: qa
# Cost: $500/month (default rate)
```

### Use Case 3: Storage Class Pricing

**Scenario:** Different costs for gold/silver/bronze storage tiers.

**Cost Model:**
```json
{
  "name": "Storage Tiers",
  "source_type": "OCP",
  "rates": [
    {
      "metric": {"name": "pvc_cost_per_month"},
      "tag_rates": {
        "tag_key": "storageclass",
        "tag_values": [
          {"tag_value": "gold", "value": 93, "default": false},
          {"tag_value": "silver", "value": 62, "default": false},
          {"tag_value": "bronze", "value": 31, "default": true}
        ]
      },
      "cost_type": "Infrastructure"
    }
  ]
}
```

**Result:**
```yaml
# PVC with gold storage class
spec:
  storageClassName: gold
# Cost: $93/month per PVC

# PVC with bronze storage class
spec:
  storageClassName: bronze
# Cost: $31/month per PVC
```

### Use Case 4: Cost Distribution Example

**Scenario:** Distribute worker unallocated costs to user projects.

**Initial Costs:**
```
Project A: $50 (25 CPU core-hours)
Project B: $150 (75 CPU core-hours)
Worker unallocated: $100 (unused capacity)
Total: $300
```

**After CPU Distribution:**
```
Project A: $50 + (25/100 × $100) = $75
Project B: $150 + (75/100 × $100) = $225
Worker unallocated: $100 - $100 = $0
Total: $300 (unchanged)
```

### Use Case 5: AWS with Markup

**Scenario:** Apply 10% markup to AWS costs.

**Cost Model:**
```json
{
  "name": "AWS 10% Markup",
  "source_type": "AWS",
  "rates": [],
  "markup": {
    "value": 10,
    "unit": "percent"
  }
}
```

**Result:**
```
Original AWS cost: $1,000
Markup cost: $1,000 × 0.10 = $100
Total cost displayed: $1,100
```

### Use Case 6: OCP-on-Cloud with Supplementary Rates

**Scenario:** OCP running on AWS with infrastructure costs from AWS and supplementary overhead from cost model.

**Cost Model:**
```json
{
  "name": "OCP on AWS",
  "source_type": "OCP",
  "rates": [
    {
      "metric": {"name": "cpu_core_usage_per_hour"},
      "tiered_rates": [{"unit": "USD", "value": 0.02}],
      "cost_type": "Supplementary"  // OpenShift overhead on top of AWS costs
    },
    {
      "metric": {"name": "memory_gb_usage_per_hour"},
      "tiered_rates": [{"unit": "USD", "value": 0.01}],
      "cost_type": "Supplementary"  // OpenShift overhead
    }
  ]
}
```

**Result:**
```
Infrastructure costs (from AWS):
  EC2 instances: $800
  EBS volumes: $200
  Total infrastructure: $1,000

Cost model supplementary costs:
  CPU: 100 core-hours × $0.02 = $2.00
  Memory: 500 GB-hours × $0.01 = $5.00
  Total supplementary: $7.00

Total OCP cost: $1,000 (AWS) + $7.00 (cost model) = $1,007.00
```

**Note:** Infrastructure costs come from the correlated AWS provider, not from cost model "Infrastructure" rates.

---

## Key Takeaways

1. **Cloud Provider Cost Models:**
   - **Limited to markup/discount** (percentage adjustment)
   - Applied to existing costs from cloud vendor reports
   - Simple multiplication: `markup_cost = cost * markup_percentage`

2. **OpenShift Cost Models:**
   - **Required for any cost calculation** (raw OCP data has no costs)
   - **Cost sources vary by deployment:**
     - **OCP-on-Cloud:** Infrastructure costs from correlated cloud provider + supplementary costs from cost model
     - **OCP-on-Prem:** All costs (infrastructure + supplementary) from cost model
   - Support **tiered rates** (usage-based), **monthly rates** (subscription-based), and **tag-based rates** (label-driven)
   - Distinguish between **Infrastructure** and **Supplementary** costs
   - Support **CPU or Memory distribution** for cost allocation

3. **Tag-Based Rates:**
   - Apply **different rates based on Kubernetes labels** (e.g., env, team, app)
   - Support **default rates** for unlabeled or unknown values
   - Generate **dynamic SQL CASE statements** at runtime
   - Handle both **pod labels** and **volume labels** (storage classes)

4. **Cost Distribution:**
   - Reallocate **unallocated and platform costs** to user projects
   - Support **CPU or Memory distribution strategies**
   - Ensure **full cluster cost attribution** to applications
   - Deduct from source namespaces to **avoid double-counting**

5. **Data Flow:**
   - **Cloud Providers:** Ingest → Store Costs → Apply Markup → Display
   - **OpenShift (OCP-on-Cloud):** Ingest OCP Usage + Cloud Costs → Match Infrastructure → Apply Cost Model (Supplementary) → Distribute Costs → Display
   - **OpenShift (OCP-on-Prem):** Ingest Usage → Apply Cost Model (Infrastructure + Supplementary) → Distribute Costs → Display

6. **API Integration:**
   - Cost models are **managed via API** (`/cost-models/`)
   - Support **CRUD operations** and **provider association**
   - Changes to cost models trigger **re-summarization** of affected date ranges

---

## Further Reading

- [Cost Management Docs](https://access.redhat.com/documentation/en-us/cost_management_service/2023/html-single/using_cost_models/index)
- [OCP CSV Processing Architecture](./csv-processing-ocp.md)
- [Distributing Cost Documentation](../distributing_cost.md)
- [Cost Model Examples](../../dev/scripts/cost_models/)

---

**Document Version:** 1.0
**Last Updated:** October 21, 2025
