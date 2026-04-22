# MIG (Multi-Instance GPU) Support Architecture

**Purpose:** This document provides a comprehensive overview of NVIDIA Multi-Instance GPU (MIG) cost tracking and allocation in Koku, enabling accurate chargeback for partitioned GPU resources in OpenShift environments.

**Last Updated:** April 10, 2026

---

## Table of Contents

1. [Overview](#overview)
2. [What is MIG?](#what-is-mig)
3. [Current GPU Implementation](#current-gpu-implementation)
4. [MIG Implementation](#mig-implementation)
5. [Data Model](#data-model)
6. [Cost Calculation](#cost-calculation)
7. [Unallocated GPU Cost](#unallocated-gpu-cost)
8. [Cost Distribution](#cost-distribution)
9. [API Changes](#api-changes)
10. [Code Architecture](#code-architecture)
11. [Examples and Scenarios](#examples-and-scenarios)
12. [Backward Compatibility](#backward-compatibility)
13. [CMMO Contract](#cmmo-contract)
14. [Testing Requirements](#testing-requirements)
15. [Troubleshooting](#troubleshooting)
16. [Key Takeaways](#key-takeaways)

---

## Overview

### What is This Feature?

A cost model capability that treats physical GPU cost as a **divisible pool**. Instead of charging a pod for a whole A100/H100, the system calculates a "slice rate" based on the proportional hardware footprint (Compute) of the MIG partition.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **MIG (Multi-Instance GPU)** | NVIDIA technology to partition a GPU into isolated instances |
| **Compute Slices** | GPU processing units allocated to a MIG instance (1-7 for A100) |
| **MIG Profile** | Configuration name like `1g.5gb`, `2g.10gb`, `3g.20gb` |
| **Slice Fraction** | Ratio of instance slices to total GPU slices (e.g., 4/7) |
| **Slice-Time** | Uptime weighted by slices: `uptime × slices` |

### Scope

- **In Scope:** NVIDIA MIG (hardware isolation) cost tracking
- **Out of Scope:** Software-level "time-slicing" (future version)

---

## What is MIG?

### Technology Overview

MIG (Multi-Instance GPU) is an NVIDIA technology available on Ampere and newer GPU architectures that allows a single physical GPU to be partitioned into up to seven isolated GPU instances.

Each MIG instance:
- Has dedicated compute resources (Streaming Multiprocessors)
- Has dedicated memory with isolation
- Has separate L2 cache paths
- Operates independently with guaranteed QoS

### MIG Profiles

| Profile | Compute Slices | Memory | Use Case |
|---------|----------------|--------|----------|
| `1g.5gb` | 1 | 5 GB | Small inference |
| `2g.10gb` | 2 | 10 GB | Medium inference |
| `3g.20gb` | 3 | 20 GB | Training/inference |
| `4g.20gb` | 4 | 20 GB | Larger workloads |
| `7g.40gb` | 7 | 40 GB | Full GPU |

### Max Slices by GPU Model

Different GPU models support different maximum slice counts:

| GPU Model | Max Instances | Architecture |
|-----------|---------------|--------------|
| A100, H100, H200, B200, GB200 | 7 | Ampere/Hopper/Blackwell |
| A30 | 4 | Ampere |
| RTX PRO 6000 | 4 | Blackwell |
| RTX PRO 5000 | 2 | Blackwell |

**Reference:** [NVIDIA MIG Supported GPUs](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-gpus.html)

**Python Lookup:**

**File:** [`koku/masu/util/ocp/common.py`](../../koku/masu/util/ocp/common.py)

```python
GPU_MAX_SLICES_BY_MODEL = {
    "A30": 4,
    "A100": 7,
    "H100": 7,
    "H200": 7,
    "B200": 7,
    "RTX PRO 6000": 4,
    "RTX PRO 5000": 2,
}
```

The lookup uses **substring matching** - e.g., "A100" matches "NVIDIA A100 80GB HBM3". See [`koku/masu/util/ocp/ocp_post_processor.py`](../../koku/masu/util/ocp/ocp_post_processor.py) `get_gpu_max_slices()`.

### GPU Model Name Normalization

GPU model names are normalized at ingestion to ensure consistent matching:

**File:** [`koku/masu/util/ocp/ocp_post_processor.py`](../../koku/masu/util/ocp/ocp_post_processor.py)

```python
# In process_dataframe():
if "gpu_model_name" in data_frame.columns:
    data_frame["gpu_model_name"] = (
        data_frame["gpu_model_name"]
        .str.replace(r"[^a-zA-Z0-9]+", " ", regex=True)
        .str.strip()
    )
```

**Effect:** `"NVIDIA A30-24GB"` → `"NVIDIA A30 24GB"`

This ensures cost model tag values (from dropdowns) match actual data regardless of punctuation differences.

### MIG Strategy

MIG strategy can be **single** or **mixed** per OpenShift node:

| Strategy | Description | Impact |
|----------|-------------|--------|
| **Single** | All GPUs partitioned the same way | Overrides `nvidia.com/gpu.count` and `nvidia.com/gpu.product` labels |
| **Mixed** | Different profiles per GPU | Uses `nvidia.com/mig-<profile>.count` labels |

**Node Labels (Mixed Strategy):**
```json
{
  "nvidia_com_mig_strategy": "mixed",
  "nvidia_com_mig_2g_20gb_count": "2",
  "nvidia_com_mig_2g_20gb_memory": "19968",
  "nvidia_com_mig_2g_20gb_product": "NVIDIA-A100-80GB-PCIe-MIG-2g.20gb",
  "nvidia_com_mig_2g_20gb_slices_gi": "2"
}
```

---

## Current GPU Implementation

### Data Flow

```
CMMO (Operator) → Parquet Files → Trino → PostgreSQL Summary → API/UI
```

### Current GPU Fields

**File:** [`koku/masu/util/ocp/common.py`](../../koku/masu/util/ocp/common.py)

```python
GPU_USAGE_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "node",
    "namespace",
    "pod",
    "gpu_uuid",
    "gpu_model_name",
    "gpu_vendor_name",
    "gpu_memory_capacity_mib",
    "gpu_pod_uptime",
}
```

### Current Cost Calculation

**File:** [`koku/masu/database/trino_sql/openshift/cost_model/monthly_cost_gpu.sql`](../../koku/masu/database/trino_sql/openshift/cost_model/monthly_cost_gpu.sql)

**Formula:**
```
cost = (rate / days_in_month) × (gpu_pod_uptime / 86400)
```

**Problem:** All pods pay based only on time, regardless of GPU partition size.

### Gap

When MIG is enabled:
- Current `gpu_uuid` represents the **physical GPU**
- Workloads run on **MIG instances** (partitions) with their own identifiers
- Cost attribution at the physical GPU level doesn't reflect actual partitioned resources consumed

---

## MIG Implementation

### New Data Fields

**From Cost Management Metrics Operator:**

| Field | Type | Description |
|-------|------|-------------|
| `mig_instance_uuid` | VARCHAR(128) | Unique identifier for the MIG instance |
| `mig_profile` | VARCHAR(32) | Partition profile (e.g., `1g.5gb`, `2g.10gb`) |
| `mig_compute_slices` | INTEGER | Number of compute slices allocated |
| `parent_gpu_uuid` | VARCHAR(128) | Reference to physical GPU UUID |
| `parent_gpu_max_slices` | INTEGER | Max slices for the GPU model |

### Implementation Strategy

1. **Cost Source of Truth:** Physical GPU's daily cost remains the base
2. **Slice-Based Allocation:** Costs calculated based on compute slice proportion
3. **Allocation Model:** Since MIG is 1:1 hardware reservation, cost is incurred when slice is assigned
4. **Unallocated Bucket:** Unused slices aggregated into "GPU Unallocated"
5. **Distribution:** Unallocated cost distributed back weighted by slice-time

---

## Data Model

### Hive/Trino Table Schema

**Table:** `openshift_gpu_usage_line_items_daily`

```sql
ALTER TABLE openshift_gpu_usage_line_items_daily ADD COLUMNS (
    mig_instance_uuid STRING,
    mig_profile STRING,
    mig_compute_slices INT,
    parent_gpu_uuid STRING,
    parent_gpu_max_slices INT
);
```

### PostgreSQL Model Updates

**File:** [`koku/reporting/provider/ocp/models.py`](../../koku/reporting/provider/ocp/models.py)

```python
class OCPGpuSummaryP(models.Model):
    # GPU identification fields
    vendor_name = models.CharField(max_length=128, null=True)
    model_name = models.CharField(max_length=128, null=True)
    mig_instance_id = models.CharField(max_length=128, null=True)  # MIG instance UUID
    gpu_uuid = models.CharField(max_length=128, null=True)  # Physical GPU UUID

    # MIG fields
    gpu_mode = models.CharField(max_length=32, null=True)  # 'dedicated' or 'MIG'
    mig_profile = models.CharField(max_length=64, null=True)  # e.g., '1g.5gb'
    mig_slice_count = models.IntegerField(null=True)
    gpu_max_slices = models.IntegerField(null=True)
    mig_strategy = models.CharField(max_length=10, null=True)
```

**Key Design Decisions:**
- `gpu_uuid` stores the physical GPU identifier for accurate GPU counting
- `mig_instance_id` stores the MIG instance identifier (NULL for dedicated GPUs)
- GPU count is computed via `Count("gpu_uuid", distinct=True)` in queries

### Column Definitions Update

**File:** [`koku/masu/util/ocp/common.py`](../../koku/masu/util/ocp/common.py)

```python
GPU_USAGE_COLUMNS = {
    # Existing fields...
    "gpu_uuid",
    "gpu_model_name",
    "gpu_vendor_name",
    "gpu_memory_capacity_mib",
    "gpu_pod_uptime",
    # NEW MIG fields
    "mig_instance_uuid",
    "mig_profile",
    "mig_compute_slices",
    "parent_gpu_uuid",
    "parent_gpu_max_slices",
}

GPU_GROUP_BY = ["node", "namespace", "pod", "gpu_uuid", "mig_instance_uuid"]

GPU_AGG = {
    # Existing aggregations...
    "mig_profile": ["max"],
    "mig_compute_slices": ["max"],
    "parent_gpu_uuid": ["max"],
    "parent_gpu_max_slices": ["max"],
}
```

### Data Validation

**File:** [`koku/masu/util/ocp/ocp_data_validator.py`](../../koku/masu/util/ocp/ocp_data_validator.py)

```python
FIELD_MAX_LENGTHS = {
    # Existing fields...
    "mig_instance_uuid": 128,
    "mig_profile": 32,
    "parent_gpu_uuid": 128,
}
```

### Parquet Processor

**File:** [`koku/masu/processor/ocp/ocp_report_parquet_processor.py`](../../koku/masu/processor/ocp/ocp_report_parquet_processor.py)

```python
numeric_columns = [
    # Existing columns...
    "gpu_memory_capacity_mib",
    "gpu_pod_uptime",
    # NEW MIG numeric columns
    "mig_compute_slices",
    "parent_gpu_max_slices",
]
```

---

## Cost Calculation

### Allocated Cost Formula

**Current:**
```
cost = (rate / days) × (uptime / 86400)
```

**With MIG:**
```
cost = (rate / days) × (uptime / 86400) × (slices / max_slices)
```

### SQL Implementation

**File:** [`koku/masu/database/trino_sql/openshift/cost_model/monthly_cost_gpu.sql`](../../koku/masu/database/trino_sql/openshift/cost_model/monthly_cost_gpu.sql)

```sql
-- Max slices lookup for backward compatibility
WITH gpu_max_slices_lookup AS (
    SELECT
        gpu_model_name,
        CASE
            WHEN gpu_model_name LIKE '%A30%' THEN 4
            WHEN gpu_model_name LIKE '%RTX PRO 5000%' THEN 2
            WHEN gpu_model_name LIKE '%RTX PRO 6000%' THEN 4
            ELSE 7
        END as default_max_slices
    FROM (SELECT DISTINCT gpu_model_name
          FROM openshift_gpu_usage_line_items_daily)
)

-- Cost calculation with slice fraction
SELECT
    ...
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9)))
      * (gpu.gpu_pod_uptime / 86400.0)
      * (
          CAST(COALESCE(gpu.mig_compute_slices, gms.default_max_slices) AS decimal(10,2))
          / CAST(COALESCE(gpu.parent_gpu_max_slices, gms.default_max_slices) AS decimal(10,2))
        ) as cost_model_gpu_cost
FROM openshift_gpu_usage_line_items_daily gpu
LEFT JOIN gpu_max_slices_lookup gms ON gms.gpu_model_name = gpu.gpu_model_name
```

### Example Calculation

**Setup:**
- Month: February (28 days)
- Monthly Rate: $2016
- Amortized Rate: $2016 / 28 = $72/day
- Hourly Rate: $72 / 24 = $3/hour
- GPU: A100 with 7 max slices

**Before (No Slice-Weighting):**

| Namespace | Uptime (hrs) | Rate | Final Cost |
|-----------|--------------|------|------------|
| ml-train  | 2 | $3 | $6 |
| inference | 6 | $3 | $18 |
| serving   | 2 | $3 | $6 |
| **Total** | | | **$30** |

**After (With Slice-Weighting):**

| Namespace | Uptime (hrs) | Slices | Slice Fraction | Rate | Final Cost |
|-----------|--------------|--------|----------------|------|------------|
| ml-train  | 2 | 4 | 4/7 = 0.571 | $3 | $3.43 |
| inference | 6 | 1 | 1/7 = 0.143 | $3 | $2.57 |
| serving   | 2 | 2 | 2/7 = 0.286 | $3 | $1.72 |
| **Total** | 10 | 7 | | | **$7.72** |

---

## Unallocated GPU Cost

### Current Logic

```sql
total_gpu_uptime = node_uptime × gpu_count
unutilized_uptime = total_gpu_uptime - sum(pod_gpu_uptime)
unallocated_cost = amortized_rate × unutilized_uptime
```

### Updated Logic (Slice-Based)

```sql
total_slice_hours = node_uptime × gpu_count × max_slices
utilized_slice_hours = sum(pod_gpu_uptime × pod_slices)
unutilized_slice_hours = total_slice_hours - utilized_slice_hours
unallocated_cost = (rate / days / 24 / max_slices) × unutilized_slice_hours
```

### Accessing Node Labels in SQL (Self-Hosted)

When GPU usage data is missing but nodes have GPU labels, the unallocated cost SQL falls back to node labels. The `node_labels` column is stored as TEXT, requiring a cast to JSONB:

**File:** [`koku/masu/database/self_hosted_sql/openshift/cost_model/monthly_cost_gpu.sql`](../../koku/masu/database/self_hosted_sql/openshift/cost_model/monthly_cost_gpu.sql)

```sql
-- Cast to JSONB and extract with normalization
LOWER(TRIM((node_ut.node_labels::jsonb)->>'nvidia_com_mig_strategy')) = 'mixed'

-- Extract numeric values
CAST(TRIM((node_ut.node_labels::jsonb)->>'nvidia_com_gpu_count') AS DECIMAL(33, 15))

-- Fallback model name from node labels (normalized)
regexp_replace(
    COALESCE(gpu.gpu_model_name, (node_ut.node_labels::jsonb)->>'nvidia_com_gpu_product'),
    '[^a-zA-Z0-9]+', ' ', 'g'
) as model
```

**Key patterns:**
- `::jsonb` cast required because `node_labels` is TEXT
- `LOWER(TRIM(...))` for case-insensitive, whitespace-tolerant comparisons
- `regexp_replace` normalizes model names to match cost model entries

### Example Calculation

**Setup:**
- Node capacity: 24 hours × 1 GPU × 7 slices = 168 slice-hours

**Utilized Slice-Hours:**

| Namespace | Uptime (hrs) | Slices | Slice-Hours |
|-----------|--------------|--------|-------------|
| ml-train  | 2 | 4 | 8 |
| inference | 6 | 1 | 6 |
| serving   | 2 | 2 | 4 |
| **Total** | | | **18** |

**Unallocated:**
```
Unutilized = 168 - 18 = 150 slice-hours
Cost per slice-hour = $3 / 7 = $0.428
Unallocated Cost = $0.428 × 150 = $64.28
```

---

## Cost Distribution

### Current Logic

```sql
distributed_cost = (namespace_uptime / total_uptime) × gpu_unallocated_cost
```

### Updated Logic (Slice-Time Weighted)

**File:** [`koku/masu/database/trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql`](../../koku/masu/database/trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql)

```sql
-- Calculate slice-weighted uptime per namespace
namespace_slice_time AS (
    SELECT
        namespace,
        node,
        DATE(interval_start) as usage_start,
        SUM(
            gpu_pod_uptime
            * COALESCE(mig_compute_slices, parent_gpu_max_slices, default_max_slices)
        ) as slice_time
    FROM openshift_gpu_usage_line_items_daily
    ...
)

-- Distribute by slice-time ratio
distributed_cost = (slice_time / total_slice_time) × unallocated_cost
```

### Example Distribution

**Unallocated Cost:** $1000

**Before (Uptime Only):**

| Namespace | Uptime (hrs) | Weight | Final Cost |
|-----------|--------------|--------|------------|
| ml-train  | 2 | 20% | $200 |
| inference | 6 | 60% | $600 |
| serving   | 2 | 20% | $200 |

**After (Slice-Time Weighted):**

| Namespace | Slices | Uptime | Slice-Hours | Weight | Final Cost |
|-----------|--------|--------|-------------|--------|------------|
| ml-train  | 4 | 2 | 8 | 44% | $444 |
| inference | 1 | 6 | 6 | 33% | $333 |
| serving   | 2 | 2 | 4 | 22% | $222 |

---

## API Changes

### GPU Report Endpoint

**Endpoint:** `GET /api/cost-management/v1/reports/openshift/gpu/`

**New Fields:**
- `gpu_mode`: `"dedicated"` or `"MIG"`
- `mig_enabled_uuids`: Array of MIG-enabled GPU UUIDs

**Example Response:**
```json
{
    "data": [
        {
            "date": "2026-01-27",
            "gpu_names": [
                {
                    "gpu_name": "nvidia_A100_node_a100",
                    "values": [
                        {
                            "gpu_vendor": "nvidia",
                            "gpu_model": "A100",
                            "gpu_mode": "MIG",
                            "mig_enabled_uuids": ["uuid-1", "uuid-2"],
                            "node": "node_a100",
                            "gpu_memory": {
                                "value": 40.0,
                                "units": "GB"
                            },
                            "gpu_count": {
                                "value": 1,
                                "units": "GPUs"
                            },
                            "cost": {...}
                        }
                    ]
                }
            ]
        }
    ]
}
```

### MIG Profiles Endpoint

**Endpoint:** `GET /api/cost-management/v1/reports/openshift/gpu/mig_profiles/`

**Required Filters:**
- `filter[vendor]` - GPU vendor (e.g., `nvidia`)
- `filter[model]` - GPU model (e.g., `H100`)
- `filter[node]` - Node name

**Example Response:**
```json
{
    "data": [
        {
            "date": "2026-01",
            "mig-profiles": [
                {
                    "mig_profile": "1g.5gb",
                    "values": [
                        {
                            "date": "2026-04-01",
                            "mig_profile": "1g.5gb",
                            "gpu_model": "A100",
                            "gpu_vendor": "nvidia",
                            "mig_id": "MIG-e46b9f71-dd65-56ef-8333-5033e349f961",
                            "gpu_name": "nvidia_A100_compute_2",
                            "node": "compute_2",
                            "compute": {
                                "value": 1,
                                "units": "g"
                            },
                            "memory": {
                                "value": 5,
                                "units": "gb"
                            },
                            "mig_slice_count": 1,
                            "gpu_max_slices": 7
                        }
                    ]
                },
                {
                    "mig_profile": "2g.10gb",
                    "values": [
                        {
                            "date": "2026-04-01",
                            "mig_profile": "2g.10gb",
                            "gpu_model": "A100",
                            "gpu_vendor": "nvidia",
                            "mig_id": "MIG-2bb570d8-41ce-5304-a0c3-447c658e7bff",
                            "gpu_name": "nvidia_A100_compute_2",
                            "node": "compute_2",
                            "compute": {
                                "value": 2,
                                "units": "g"
                            },
                            "memory": {
                                "value": 10,
                                "units": "gb"
                            },
                            "mig_slice_count": 2,
                            "gpu_max_slices": 7
                        }
                    ]
                }
            ]
        }
    ]
}
```

### New Group-By and Filter Options

| Option | Values |
|--------|--------|
| Group by | `mig_profile` |
| Filter by | `mig_profile`, `gpu_instance_uuid` |

### GPU Count Calculation

GPU count in API responses uses `Count("gpu_uuid", distinct=True)` to accurately count unique physical GPUs across aggregated rows.

**File:** [`koku/api/report/ocp/provider_map.py`](../../koku/api/report/ocp/provider_map.py)

```python
"gpu_count": Count("gpu_uuid", distinct=True),
```

**Why this matters:**
- Summary table groups data by (namespace, node, model, mig_profile, date)
- A node with 4 GPUs creates 4 rows with different `gpu_uuid` values
- `Count(DISTINCT)` correctly aggregates to `gpu_count: 4` across daily/monthly views

**Previous approach (deprecated):** Used complex RawSQL subqueries in `query_handler.py`. This was replaced with the simpler `Count(DISTINCT)` annotation in `provider_map.py`.

---

## Code Architecture

### File Structure

```
koku/
├── masu/
│   ├── util/ocp/
│   │   ├── common.py                    # GPU_USAGE_COLUMNS, GPU_AGG, GPU_MAX_SLICES_BY_MODEL
│   │   └── ocp_post_processor.py        # gpu_model_name normalization, get_gpu_max_slices()
│   │
│   ├── processor/ocp/
│   │   └── ocp_report_parquet_processor.py  # numeric_columns
│   │
│   └── database/
│       ├── trino_sql/openshift/
│       │   ├── cost_model/
│       │   │   ├── monthly_cost_gpu.sql     # Allocated + Unallocated cost (SaaS)
│       │   │   └── distribute_cost/
│       │   │       └── distribute_unallocated_gpu_cost.sql
│       │   └── ui_summary/
│       │       └── reporting_ocp_gpu_summary_p_usage_only.sql
│       │
│       ├── self_hosted_sql/openshift/
│       │   ├── cost_model/
│       │   │   └── monthly_cost_gpu.sql     # Allocated + Unallocated cost (On-Prem)
│       │   └── ui_summary/
│       │       └── reporting_ocp_gpu_summary_p_usage_only.sql
│       │
│       └── sql/openshift/ui_summary/
│           └── reporting_ocp_gpu_summary_p.sql  # Summary from daily_summary
│
├── reporting/provider/ocp/
│   └── models.py                        # OCPGpuSummaryP
│
└── api/report/ocp/
    ├── provider_map.py                  # GPU annotations, Count(DISTINCT gpu_uuid)
    └── serializers.py                   # OCPGpuSerializer
```

### Key Files Summary

| File | Purpose |
|------|---------|
| `ocp_post_processor.py` | Normalizes `gpu_model_name`, looks up `gpu_max_slices` |
| `monthly_cost_gpu.sql` | Calculates allocated cost (slice-weighted) and unallocated cost |
| `reporting_ocp_gpu_summary_p*.sql` | Populates summary table with `mig_instance_id`, `gpu_uuid` |
| `provider_map.py` | Defines API annotations including `Count("gpu_uuid", distinct=True)` |
| `models.py` | `OCPGpuSummaryP` model with MIG fields |

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               DATA INGESTION FLOW                             │
└──────────────────────────────────────────────────────────────────────────────┘

   CMMO (Operator)              Kafka                    Koku Processing
   ┌──────────────┐         ┌──────────────┐         ┌──────────────────────┐
   │ GPU CSV with │         │   Upload     │         │ kafka_msg_handler.py │
   │ MIG fields   │────────▶│   Topic      │────────▶│ extract_payload()    │
   └──────────────┘         └──────────────┘         └──────────┬───────────┘
                                                                │
                                                                ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  ocp/common.py - GPU_USAGE_COLUMNS                                        │
   │  + mig_instance_uuid, mig_profile, mig_compute_slices,                   │
   │  + parent_gpu_uuid, parent_gpu_max_slices                                │
   └──────────────────────────────────────────────────────────────────────────┘
                                                                │
                                                                ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  ocp_post_processor.py                                                    │
   │  validate_and_sanitize_dataframe()                                       │
   │  _generate_daily_data() with GPU_GROUP_BY, GPU_AGG                       │
   └──────────────────────────────────────────────────────────────────────────┘
                                                                │
                                                                ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  ocp_report_parquet_processor.py                                          │
   │  numeric_columns += mig_compute_slices, parent_gpu_max_slices            │
   └──────────────────────────────────────────────────────────────────────────┘
                                                                │
                                                                ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  Hive/Trino: openshift_gpu_usage_line_items_daily                         │
   │  + mig_instance_uuid, mig_profile, mig_compute_slices,                   │
   │  + parent_gpu_uuid, parent_gpu_max_slices                                │
   └──────────────────────────────────────────────────────────────────────────┘
                                                                │
                        ┌───────────────────────────────────────┴─────────────┐
                        ▼                                                     ▼
   ┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
   │  monthly_cost_gpu.sql               │    │  distribute_unallocated_gpu_cost.sql│
   │                                     │    │                                     │
   │  Allocated Cost:                    │    │  Distribution:                      │
   │  rate × uptime × (slices/max)       │    │  slice_time / total × cost          │
   │                                     │    │                                     │
   │  Unallocated Cost:                  │    └─────────────────────────────────────┘
   │  rate × unutilized_slice_hours      │
   └─────────────────────────────────────┘
                        │
                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  PostgreSQL: reporting_ocpusagelineitem_daily_summary                     │
   │  all_labels JSON includes:                                                │
   │    'gpu-model', 'gpu-vendor', 'gpu-memory-mib', 'mig-profile',           │
   │    'mig-slice-count', 'gpu-max-slices', 'mig-strategy',                  │
   │    'mig-memory-mib', 'gpu-mode', 'mig-instance-id'                       │
   │  cost_model_gpu_cost (now slice-weighted)                                │
   └──────────────────────────────────────────────────────────────────────────┘
                        │
                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  PostgreSQL: reporting_ocp_gpu_summary_p                                  │
   │  + mig_profile, mig_instance_id, gpu_uuid                       │
   └──────────────────────────────────────────────────────────────────────────┘
```

### all_labels JSON Structure

The `all_labels` column in `reporting_ocpusagelineitem_daily_summary` contains GPU metadata as JSON:

```json
{
  "gpu-model": "A100",
  "gpu-vendor": "nvidia",
  "gpu-memory-mib": "40960",
  "mig-profile": "1g.5gb",
  "mig-slice-count": "1",
  "gpu-max-slices": "7",
  "mig-strategy": "mixed",
  "mig-memory-mib": "5120",
  "gpu-mode": "MIG",
  "mig-instance-id": "MIG-abc123"
}
```

**PostgreSQL extraction:**
```sql
all_labels->>'mig-profile' as mig_profile,
all_labels->>'mig-instance-id' as mig_instance_id
```

**Trino extraction:**
```sql
json_extract_scalar(CAST(all_labels AS json), '$.mig-profile') as mig_profile
```

---

## Examples and Scenarios

### Scenario 1: Single A100 with MIG

**Setup:**
- Physical Device: NVIDIA A100 ($70/day)
- Configuration: One `4g.20gb` slice (4/7 of total GPU resources)
- Pod runs for 24 hours

**Result:**
- Pod allocated cost: $70 × (4/7) = $40
- GPU Unallocated: $70 × (3/7) = $30

### Scenario 2: Multi-Namespace Sharing

**Setup:**
- A100 rate: $1000/month (30 days) = $33.33/day
- Three namespaces sharing MIG partitions:

| Namespace | MIG Profile | Slices | Uptime (hrs) |
|-----------|-------------|--------|--------------|
| ml-train  | 3g.20gb | 4 | 2 |
| inference | 1g.5gb | 1 | 6 |
| serving   | 2g.10gb | 2 | 2 |

**Allocated Costs:**

| Namespace | Formula | Cost |
|-----------|---------|------|
| ml-train  | $33.33 × (2/24) × (4/7) | $1.59 |
| inference | $33.33 × (6/24) × (1/7) | $1.19 |
| serving   | $33.33 × (2/24) × (2/7) | $0.79 |
| **Total Allocated** | | **$3.57** |

**Unallocated Cost:**
- Total slice-hours: 168 (24 hrs × 7 slices)
- Utilized: 8 + 6 + 4 = 18 slice-hours
- Unutilized: 150 slice-hours
- Cost: $33.33 × (150/168) = $29.76

**Distribution (if enabled):**

| Namespace | Slice-Hours | Weight | Distributed |
|-----------|-------------|--------|-------------|
| ml-train  | 8 | 44% | $13.23 |
| inference | 6 | 33% | $9.92 |
| serving   | 4 | 22% | $6.61 |

### Scenario 3: Mixed Strategy Node

**Setup:**
- Node with 2 A100 GPUs
- GPU 1: 7× `1g.5gb` partitions
- GPU 2: 1× `3g.20gb` + 2× `2g.10gb` partitions

**Node Labels:**
```json
{
  "nvidia_com_mig_strategy": "mixed",
  "nvidia_com_mig_1g_5gb_count": "7",
  "nvidia_com_mig_2g_10gb_count": "2",
  "nvidia_com_mig_3g_20gb_count": "1"
}
```

**Cost Tracking:**
- Each MIG instance tracked separately via `mig_instance_uuid`
- Costs calculated per instance based on slice count
- Parent GPU identified via `parent_gpu_uuid`

---

## Backward Compatibility

### Non-MIG GPUs

When MIG fields are `NULL` (non-MIG GPU or older CMMO):

| Field | Default Behavior |
|-------|------------------|
| `mig_instance_uuid` | `NULL` - use `gpu_uuid` as resource_id |
| `mig_profile` | `NULL` → stored as `'full'` in all_labels |
| `mig_compute_slices` | `NULL` → defaults to `parent_gpu_max_slices` or model lookup |
| `parent_gpu_uuid` | `NULL` - not needed for non-MIG |
| `parent_gpu_max_slices` | `NULL` → uses model lookup table |

### COALESCE Chain

```sql
effective_slices = COALESCE(
    mig_compute_slices,           -- 1st: Use MIG slices if present
    parent_gpu_max_slices,        -- 2nd: Use parent max if present
    gpu_max_slices_lookup.value   -- 3rd: Fall back to model lookup
)
```

For non-MIG GPUs: `slice_fraction = 7/7 = 1.0` (no cost change)

---

## CMMO Contract

The Cost Management Metrics Operator must provide these fields when MIG is detected:

| CSV Column | Type | Example | Required |
|------------|------|---------|----------|
| `mig_instance_uuid` | string | `MIG-GPU-abc123-0-0` | Yes (if MIG) |
| `mig_profile` | string | `1g.5gb` | Yes (if MIG) |
| `mig_compute_slices` | integer | `1` | Yes (if MIG) |
| `parent_gpu_uuid` | string | `GPU-abc123` | Yes (if MIG) |
| `parent_gpu_max_slices` | integer | `7` | Yes (if MIG) |

For non-MIG GPUs, all MIG columns should be empty/null in the CSV.

---

## Testing Requirements

### Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_mig_cost_calculation_single_slice` | Verify 1g.5gb gets 1/7 of A100 cost |
| `test_mig_cost_calculation_multi_slice` | Verify 3g.20gb gets 3/7 of A100 cost |
| `test_mig_cost_a30_max_slices` | Verify A30 uses 4 as max slices |
| `test_non_mig_gpu_unchanged` | Verify non-MIG GPUs calculate at full rate |
| `test_unallocated_slice_time_calculation` | Verify unallocated uses slice-hours |
| `test_distribution_by_slice_time` | Verify distribution weights by slice-time |
| `test_mig_data_validation` | Verify MIG field validation rules |
| `test_backward_compatibility_null_mig` | Verify NULL MIG fields work correctly |

### Integration Tests

| Test Case | Description |
|-----------|-------------|
| `test_mig_ingestion_pipeline` | End-to-end MIG data ingestion |
| `test_mig_cost_model_application` | Cost model with MIG workloads |
| `test_mig_api_groupby` | API group-by `mig_profile` |
| `test_mig_api_filter` | API filter by `mig_profile` |

---

## Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `operator does not exist: text ->> unknown` | `node_labels` accessed without JSONB cast | Cast: `(node_labels::jsonb)->>'key'` |
| `column must appear in GROUP BY clause` | Accessing raw column in aggregated query | Add to `GROUP BY` or wrap in aggregate |
| `GPU model 'X' not found in MIG max slices mapping` | Model name doesn't match lookup | Use substring matching in `GPU_MAX_SLICES_BY_MODEL` |

### GPU Model Name Mismatch

If cost model entries don't match data:

1. Check raw data: `SELECT DISTINCT gpu_model_name FROM openshift_gpu_usage_line_items_daily`
2. Verify normalization: Both data and cost model values should go through `regexp_replace(..., '[^a-zA-Z0-9]+', ' ', 'g')`
3. Update `ocp_post_processor.py` if ingestion-time normalization is needed

### Node Labels Debugging

When GPU usage data is missing, the system falls back to node labels. Debug with:

```sql
SELECT node, node_labels::jsonb->>'nvidia_com_gpu_count',
       node_labels::jsonb->>'nvidia_com_gpu_product',
       LOWER(TRIM(node_labels::jsonb->>'nvidia_com_mig_strategy'))
FROM reporting_ocpnodeuptimelineitem
WHERE node_labels::jsonb->>'nvidia_com_gpu_count' IS NOT NULL;
```

### Trino vs PostgreSQL SQL Differences

| Feature | PostgreSQL | Trino |
|---------|------------|-------|
| JSONB access | `(col::jsonb)->>'key'` | `json_extract_scalar(col, '$.key')` |
| Map construction | `jsonb_build_object(...)` | `map(ARRAY[], ARRAY[])` |
| UUID generation | `gen_random_uuid()` | `uuid()` |

**Important:** The `all_labels` column is JSON in PostgreSQL but a MAP in Trino. Summary SQL must use appropriate syntax for each.

---

## Key Takeaways

1. **MIG Divides GPU Cost:** Physical GPU cost is split proportionally by compute slices
2. **Slice-Time Weighting:** Both uptime AND slices matter for cost attribution
3. **Unallocated Tracking:** Unused slice-hours become "GPU Unallocated" costs
4. **Distribution:** Unallocated costs distributed by slice-time ratio
5. **Backward Compatible:** Non-MIG GPUs continue to work unchanged
6. **Dynamic Max Slices:** Different GPU models have different maximums
7. **Model Name Normalization:** GPU model names are normalized at ingestion to ensure cost model matching
8. **GPU Count via DISTINCT:** Use `Count("gpu_uuid", distinct=True)` for accurate GPU counts

---

## Further Reading

- [Cost Models Architecture](./cost-models.md)
- [OCP CSV Processing Architecture](./csv-processing-ocp.md)
- [NVIDIA MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)
- [NVIDIA MIG Supported GPUs](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-gpus.html)

---

**Document Version:** 1.1
**Last Updated:** April 10, 2026
