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

**File:** `koku/masu/database/aws_report_db_accessor.py`

```python
def populate_markup_cost(self, provider_uuid, markup, start_date, end_date, bill_ids=None):
    """Set markup costs in the database."""
    with schema_context(self.schema):
        date_filters = {"usage_start__gte": start_date, "usage_start__lte": end_date}

        for bill_id in bill_ids:
            # Apply markup to AWS cost line items
            AWSCostEntryLineItemDailySummary.objects.filter(
                cost_entry_bill_id=bill_id,
                **date_filters
            ).update(
                markup_cost=(F("unblended_cost") * markup),
                markup_cost_blended=(F("blended_cost") * markup),
                markup_cost_savingsplan=(F("savingsplan_effective_cost") * markup),
                markup_cost_amortized=(F("calculated_amortized_cost") * markup),
            )
```

**Key Points:**
- Markup is a decimal (e.g., `0.10` for 10%)
- Applied to **all cost types**: unblended, blended, savings plan, amortized
- Stored in separate `markup_cost*` columns in the database
- Same pattern used for Azure (`pretax_cost`) and GCP

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

**File:** `koku/masu/database/sql/openshift/cost_model/usage_costs.sql`

```sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    ...
)
SELECT
    sum(coalesce(pod_usage_cpu_core_hours, 0)) * {{cpu_core_usage_per_hour}}
        + sum(coalesce(pod_request_cpu_core_hours, 0)) * {{cpu_core_request_per_hour}}
        + sum(coalesce(pod_effective_usage_cpu_core_hours, 0)) * {{cpu_core_effective_usage_per_hour}}
        + sum(coalesce(pod_effective_usage_cpu_core_hours, 0)) * {{node_core_cost_per_hour}}
        + sum(coalesce(pod_effective_usage_cpu_core_hours, 0)) * {{cluster_core_cost_per_hour}}
        as cost_model_cpu_cost,

    sum(coalesce(pod_usage_memory_gigabyte_hours, 0)) * {{memory_gb_usage_per_hour}}
        + sum(coalesce(pod_request_memory_gigabyte_hours, 0)) * {{memory_gb_request_per_hour}}
        + sum(coalesce(pod_effective_usage_memory_gigabyte_hours, 0)) * {{memory_gb_effective_usage_per_hour}}
        as cost_model_memory_cost,

    sum(coalesce(persistentvolumeclaim_usage_gigabyte_months, 0)) * {{storage_gb_usage_per_month}}
        + sum(coalesce(volume_request_storage_gigabyte_months, 0)) * {{storage_gb_request_per_month}}
        as cost_model_volume_cost
FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2025-01-01'
  AND usage_start < '2025-02-01'
GROUP BY usage_start, cluster_id, namespace, pod_labels;
```

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

**File:** `koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql`

```sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_cpu_cost,
    cost_model_memory_cost,
    monthly_cost_type,
    ...
)
SELECT
    CASE
        WHEN {{cost_type}} = 'Cluster' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours)
                 / max(cluster_capacity_cpu_core_hours)
                 * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours)
                 / max(node_capacity_cpu_core_hours)
                 * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node_Core_Month' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours)
                 / max(node_capacity_cpu_core_hours)
                 * max(node_capacity_cpu_cores)
                 * {{rate}}::decimal
        ELSE 0
    END AS cost_model_cpu_cost,

    {{cost_type}} as monthly_cost_type
FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2025-01-01'
  AND usage_start < '2025-02-01'
  AND namespace IS NOT NULL
GROUP BY usage_start, cluster_id, node, namespace, pod_labels;
```

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

**File:** `koku/masu/processor/ocp/ocp_cost_model_cost_updater.py`

```python
def _build_node_tag_cost_case_statements(
    self, rate_dict, start_date, default_rate_dict={}, unallocated=False, node_core="", amortized=True
):
    """Given a tag key, value, and rate return a CASE SQL statement for tag-based pricing."""
    case_dict = {}

    cpu_distribution_term = """
        sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours)
    """
    memory_distribution_term = """
        sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours)
    """

    for tag_key, tag_value_rates in rate_dict.items():
        cpu_statement_list = ["CASE"]
        memory_statement_list = ["CASE"]

        for tag_value, rate_value in tag_value_rates.items():
            label_condition = f"pod_labels->>'{tag_key}'='{tag_value}'"
            rate = get_amortized_monthly_cost_model_rate(rate_value, start_date) if amortized else rate_value

            cpu_statement_list.append(
                f"""
                    WHEN {label_condition}
                        THEN {cpu_distribution_term} * {rate}::decimal
                """
            )
            memory_statement_list.append(
                f"""
                    WHEN {label_condition}
                        THEN {memory_distribution_term} * {rate}::decimal
                """
            )

        # Add default rate
        if default_rate_dict:
            rate_value = default_rate_dict.get(tag_key, {}).get("default_value", 0)
            rate = get_amortized_monthly_cost_model_rate(rate_value, start_date) if amortized else rate_value

            cpu_statement_list.append(
                f"ELSE {cpu_distribution_term} * {rate}::decimal"
            )
            memory_statement_list.append(
                f"ELSE {memory_distribution_term} * {rate}::decimal"
            )

        cpu_statement_list.append("END as cost_model_cpu_cost")
        memory_statement_list.append("END as cost_model_memory_cost")

        if self._distribution == "cpu":
            case_dict[tag_key] = (
                "\n".join(cpu_statement_list),
                "0::decimal as cost_model_memory_cost",
                "0::decimal as cost_model_volume_cost",
            )
        elif self._distribution == "memory":
            case_dict[tag_key] = (
                "0::decimal as cost_model_cpu_cost",
                "\n".join(memory_statement_list),
                "0::decimal as cost_model_volume_cost",
            )

    return case_dict
```

### Generated SQL Example

**Input Rate:**
```json
{
  "env": {
    "prod": 0.10,
    "dev": 0.05,
    "default_value": 0.03
  }
}
```

**Generated SQL:**

**File:** `koku/masu/database/sql/openshift/cost_model/node_cost_by_tag.sql`

```sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_cpu_cost,
    cost_model_memory_cost,
    monthly_cost_type,
    ...
)
SELECT
    CASE
        WHEN pod_labels->>'env' = 'prod' THEN
            sum(pod_effective_usage_cpu_core_hours)
            / max(node_capacity_cpu_core_hours)
            * 0.10::decimal
        WHEN pod_labels->>'env' = 'dev' THEN
            sum(pod_effective_usage_cpu_core_hours)
            / max(node_capacity_cpu_core_hours)
            * 0.05::decimal
        ELSE
            sum(pod_effective_usage_cpu_core_hours)
            / max(node_capacity_cpu_core_hours)
            * 0.03::decimal
    END as cost_model_cpu_cost,

    0 as cost_model_memory_cost,
    'Node' as monthly_cost_type
FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2025-01-01'
  AND usage_start < '2025-02-01'
  AND pod_labels ? 'env'  -- Only rows with 'env' label
GROUP BY usage_start, cluster_id, node, namespace, pod_labels;
```

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

**File:** `koku/masu/database/sql/openshift/cost_model/monthly_cost_persistentvolumeclaim_by_tag.sql`

```python
def _build_volume_tag_cost_case_statements(self, rate_dict, start_date, default_rate_dict={}):
    """Generate CASE statement for PVC tag-based pricing."""
    case_dict = {}

    for tag_key, tag_value_rates in rate_dict.items():
        volume_statement_list = ["CASE"]

        for tag_value, rate_value in tag_value_rates.items():
            rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
            volume_statement_list.append(
                f"""
                    WHEN volume_labels->>'{tag_key}'='{tag_value}'
                        THEN {rate}::decimal / vc.pvc_count
                """
            )

        if default_rate_dict:
            rate_value = default_rate_dict.get(tag_key, {}).get("default_value", 0)
            rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
            volume_statement_list.append(f"ELSE {rate}::decimal / vc.pvc_count")

        volume_statement_list.append("END as cost_model_volume_cost")

        case_dict[tag_key] = (
            "0::decimal as cost_model_cpu_cost",
            "0::decimal as cost_model_memory_cost",
            "\n".join(volume_statement_list),
        )

    return case_dict
```

**Generated SQL:**
```sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_volume_cost,
    monthly_cost_type,
    ...
)
SELECT
    CASE
        WHEN volume_labels->>'storageclass' = 'gold' THEN 93::decimal / vc.pvc_count
        WHEN volume_labels->>'storageclass' = 'silver' THEN 62::decimal / vc.pvc_count
        WHEN volume_labels->>'storageclass' = 'bronze' THEN 31::decimal / vc.pvc_count
        ELSE 31::decimal / vc.pvc_count  -- Default
    END as cost_model_volume_cost
FROM reporting_ocpusagelineitem_daily_summary
WHERE volume_labels ? 'storageclass'
  AND usage_start >= '2025-01-01'
  AND usage_start < '2025-02-01';
```

### Unallocated Costs for Tag-Based Rates

**Concept:** When applying tag-based monthly rates, **unallocated node capacity** must also be costed.

**Unallocated Capacity:**
```
unallocated = node_capacity - pod_effective_usage
```

**SQL for Unallocated Costs:**
```sql
-- Unallocated costs assigned to "Worker unallocated" or "Platform unallocated" namespaces
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    namespace,
    cost_model_cpu_cost,
    monthly_cost_type,
    ...
)
SELECT
    CASE max(nodes.node_role)
        WHEN 'master' THEN 'Platform unallocated'
        WHEN 'infra' THEN 'Platform unallocated'
        WHEN 'worker' THEN 'Worker unallocated'
    END as namespace,

    CASE
        WHEN pod_labels->>'env' = 'prod' THEN
            (max(node_capacity_cpu_core_hours) - sum(pod_effective_usage_cpu_core_hours))
            / max(node_capacity_cpu_core_hours)
            * 0.10::decimal
        WHEN pod_labels->>'env' = 'dev' THEN
            (max(node_capacity_cpu_core_hours) - sum(pod_effective_usage_cpu_core_hours))
            / max(node_capacity_cpu_core_hours)
            * 0.05::decimal
    END as cost_model_cpu_cost,

    'Node' as monthly_cost_type
FROM reporting_ocpusagelineitem_daily_summary
WHERE pod_labels ? 'env';
```

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

**File:** `koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_worker_cost.sql`

**Formula (CPU Distribution):**
```
distributed_cost = (project_cpu_usage / total_user_project_cpu_usage) * worker_unallocated_cost
```

**SQL Implementation:**
```sql
WITH worker_cost AS (
    -- Calculate total worker unallocated cost
    SELECT
        usage_start,
        cluster_id,
        source_uuid,
        SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0) +
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0)
        ) as worker_cost
    FROM reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'Worker unallocated'
      AND usage_start >= '2025-01-01'
      AND usage_start < '2025-02-01'
    GROUP BY usage_start, cluster_id, source_uuid
),
user_project_sum AS (
    -- Calculate total usage of all user projects
    SELECT
        usage_start,
        cluster_id,
        source_uuid,
        SUM(pod_effective_usage_cpu_core_hours) as usage_cpu_sum,
        SUM(pod_effective_usage_memory_gigabyte_hours) as usage_memory_sum
    FROM reporting_ocpusagelineitem_daily_summary
    WHERE namespace NOT IN ('Worker unallocated', 'Platform unallocated')
      AND usage_start >= '2025-01-01'
      AND usage_start < '2025-02-01'
    GROUP BY usage_start, cluster_id, source_uuid
)
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    distributed_cost,
    ...
)
SELECT
    CASE
        WHEN {{distribution}} = 'cpu' AND namespace != 'Worker unallocated' THEN
            (sum(pod_effective_usage_cpu_core_hours) / max(usage_cpu_sum))
            * max(worker_cost)::decimal
        WHEN {{distribution}} = 'memory' AND namespace != 'Worker unallocated' THEN
            (sum(pod_effective_usage_memory_gigabyte_hours) / max(usage_memory_sum))
            * max(worker_cost)::decimal
        WHEN namespace = 'Worker unallocated' THEN
            -- Deduct from Worker unallocated to avoid double-counting
            0 - SUM(
                COALESCE(infrastructure_raw_cost, 0) +
                COALESCE(cost_model_cpu_cost, 0) +
                COALESCE(cost_model_memory_cost, 0)
            )
        ELSE 0
    END AS distributed_cost
FROM reporting_ocpusagelineitem_daily_summary
JOIN worker_cost ON ...
JOIN user_project_sum ON ...;
```

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

**File:** `koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_platform_cost.sql`

**Formula:**
```
distributed_cost = (project_usage / total_non_platform_usage) * platform_cost
```

**SQL Pattern:**
```sql
WITH platform_cost AS (
    SELECT
        usage_start,
        cluster_id,
        SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0)
        ) as platform_cost
    FROM reporting_ocpusagelineitem_daily_summary
    WHERE cost_category_id IS NOT NULL
      AND category_name = 'Platform'
    GROUP BY usage_start, cluster_id
)
SELECT
    CASE
        WHEN {{distribution}} = 'cpu' AND category_name != 'Platform' THEN
            (sum(pod_effective_usage_cpu_core_hours) / max(usage_cpu_sum))
            * max(platform_cost)::decimal
        WHEN category_name = 'Platform' THEN
            0 - SUM(COALESCE(infrastructure_raw_cost, 0) + ...)
        ELSE 0
    END AS distributed_cost
FROM reporting_ocpusagelineitem_daily_summary;
```

### 3. Unattributed Storage Distribution

**Purpose:** Distribute storage costs that aren't tied to specific PVCs.

**File:** `koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_storage_cost.sql`

### 4. Unattributed Network Distribution

**Purpose:** Distribute network costs that aren't tied to specific pods.

**File:** `koku/masu/database/sql/openshift/cost_model/distribute_cost/distribute_unattributed_network_cost.sql`

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

**File:** `koku/cost_models/models.py`

```python
class CostModel(models.Model):
    """A collection of rates used to calculate cost against resource usage data."""

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.TextField()
    description = models.TextField()
    source_type = models.CharField(max_length=50, choices=Provider.PROVIDER_CHOICES)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)
    rates = JSONField(default=dict)
    markup = JSONField(encoder=DjangoJSONEncoder, default=dict)
    distribution = models.TextField(choices=DISTRIBUTION_CHOICES, default=DEFAULT_DISTRIBUTION)
    distribution_info = JSONField(default=dict)
    currency = models.TextField(default=KOKU_DEFAULT_CURRENCY)

    class Meta:
        db_table = "cost_model"
        ordering = ["name"]


class CostModelMap(models.Model):
    """Map for provider and rate objects."""

    provider_uuid = models.UUIDField(editable=False, unique=False, null=False)
    cost_model = models.ForeignKey("CostModel", null=True, on_delete=models.CASCADE)

    class Meta:
        ordering = ["-id"]
        unique_together = ("provider_uuid", "cost_model")
        db_table = "cost_model_map"
```

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

**File:** `koku/masu/processor/ocp/ocp_cost_model_cost_updater.py`

**Class:** `OCPCostModelCostUpdater`

**Key Methods:**

```python
class OCPCostModelCostUpdater(OCPCloudUpdaterBase):
    """Class to update OCP report summary data with charge information."""

    def __init__(self, schema, provider):
        """Initialize with schema and provider, load cost model."""
        super().__init__(schema, provider, None)
        self._cluster_id = get_cluster_id_from_provider(self._provider_uuid)

        with CostModelDBAccessor(self._schema, self._provider_uuid) as cost_model_accessor:
            self._cost_model = cost_model_accessor.cost_model
            self._infra_rates = cost_model_accessor.infrastructure_rates
            self._tag_infra_rates = cost_model_accessor.tag_infrastructure_rates
            self._supplementary_rates = cost_model_accessor.supplementary_rates
            self._tag_supplementary_rates = cost_model_accessor.tag_supplementary_rates
            self._distribution = cost_model_accessor.distribution_info.get("distribution_type", "cpu")

    def update_summary_cost_model_costs(self, start_date, end_date):
        """Update OCP report summary with cost model cost calculations."""
        # 1. Update usage-based costs
        self._update_usage_costs(start_date, end_date)

        # 2. Update monthly costs (cluster, node, PVC)
        self._update_monthly_cost(start_date, end_date)

        # 3. Update tag-based usage costs
        self._update_tag_usage_costs(start_date, end_date)

        # 4. Update tag-based monthly costs
        self._update_monthly_tag_based_cost(start_date, end_date)

        # 5. Apply markup
        self._update_markup_cost(start_date, end_date)

        # 6. Distribute costs
        self._distribute_costs(start_date, end_date)

    def _update_usage_costs(self, start_date, end_date):
        """Populate usage-based cost model costs (CPU, memory, storage)."""
        # Generate SQL parameters from rates
        sql_params = self._sql_params.get_sql_params("usage_costs")

        # Execute SQL template
        sql = self._prepare_template("usage_costs.sql")
        self._execute_sql(sql, sql_params)

    def _update_monthly_cost(self, start_date, end_date):
        """Populate monthly cost model costs (node, cluster, PVC)."""
        # Execute for each monthly cost type
        for cost_type in ["Node", "Cluster", "Node_Core_Month", "PVC"]:
            sql_params = self._sql_params.get_sql_params(cost_type)
            sql = self._prepare_template("monthly_cost.sql")
            self._execute_sql(sql, sql_params)

    def _update_tag_usage_costs(self, start_date, end_date):
        """Update tag-based usage costs."""
        # For each tag key with rates
        for tag_key, tag_rates in self._tag_infra_rates.items():
            # Generate CASE statements
            case_statements = self._build_tag_cost_case_statements(tag_rates, start_date)

            # Execute SQL with dynamic CASE statements
            sql = self._prepare_template("tag_usage_costs.sql")
            self._execute_sql(sql, {"tag_key": tag_key, "case_statements": case_statements})

    def _update_monthly_tag_based_cost(self, start_date, end_date):
        """Update tag-based monthly costs (node, PVC)."""
        # Similar to _update_tag_usage_costs but for monthly rates
        pass

    def _build_tag_cost_case_statements(self, rate_dict, start_date, default_rate_dict={}):
        """Generate SQL CASE statements for tag-based pricing."""
        # Returns dictionary of {tag_key: (cpu_case, memory_case, volume_case)}
        pass

    def _distribute_costs(self, start_date, end_date):
        """Distribute unallocated and platform costs."""
        # Execute distribution SQL for worker, platform, storage, network
        pass
```

### Cost Model DB Accessor

**File:** `koku/masu/database/cost_model_db_accessor.py`

```python
class CostModelDBAccessor(ReportDBAccessorBase):
    """Class to interact with cost model database tables."""

    def __init__(self, schema, provider_uuid):
        """Initialize accessor with schema and provider."""
        super().__init__(schema)
        self._provider_uuid = provider_uuid
        self._cost_model = self._get_cost_model()

    @property
    def cost_model(self):
        """Return the cost model object."""
        return self._cost_model

    @property
    def infrastructure_rates(self):
        """Extract infrastructure rates from cost model."""
        return self._parse_rates("Infrastructure")

    @property
    def supplementary_rates(self):
        """Extract supplementary rates from cost model."""
        return self._parse_rates("Supplementary")

    @property
    def tag_infrastructure_rates(self):
        """Extract tag-based infrastructure rates."""
        return self._parse_tag_rates("Infrastructure")

    @property
    def tag_supplementary_rates(self):
        """Extract tag-based supplementary rates."""
        return self._parse_tag_rates("Supplementary")

    @property
    def markup(self):
        """Extract markup percentage."""
        markup_dict = self._cost_model.markup
        return markup_dict.get("value", 0) / 100

    @property
    def distribution_info(self):
        """Extract distribution configuration."""
        return self._cost_model.distribution_info or {"distribution_type": "cpu"}
```

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

**Task:** `update_summary_tables`

**File:** `koku/masu/processor/tasks.py`

```python
@shared_task(name="update_summary_tables")
def update_summary_tables(schema_name, provider_type, provider_uuid, start_date, end_date, queue_name=None):
    """Update report summary tables with cost model costs."""

    # For OCP providers
    if provider_type == Provider.PROVIDER_OCP:
        # Apply cost model
        cost_updater = OCPCostModelCostUpdater(schema_name, provider_uuid)
        cost_updater.update_summary_cost_model_costs(start_date, end_date)

    # For cloud providers
    elif provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP]:
        # Apply markup
        with CostModelDBAccessor(schema_name, provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            if markup:
                accessor = get_db_accessor(provider_type, schema_name)
                accessor.populate_markup_cost(provider_uuid, markup, start_date, end_date)
```

### SQL Template Rendering

**Jinja2 Templates:**

Cost model SQL files use **Jinja2 templating** for dynamic rate injection:

```sql
-- Template: usage_costs.sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_cpu_cost,
    ...
)
SELECT
    sum(pod_usage_cpu_core_hours) * {{cpu_core_usage_per_hour}}
        + sum(pod_request_cpu_core_hours) * {{cpu_core_request_per_hour}}
        + sum(pod_effective_usage_cpu_core_hours) * {{cpu_core_effective_usage_per_hour}}
        as cost_model_cpu_cost
FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}};
```

**Rendered SQL:**
```sql
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cost_model_cpu_cost,
    ...
)
SELECT
    sum(pod_usage_cpu_core_hours) * 0.007
        + sum(pod_request_cpu_core_hours) * 0.2
        + sum(pod_effective_usage_cpu_core_hours) * 0.05
        as cost_model_cpu_cost
FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2025-01-01'
  AND usage_start <= '2025-01-31';
```

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
