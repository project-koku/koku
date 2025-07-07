# Optimizing Trino Query Performance: Leveraging Partition Pruning

When querying large datasets in Trino, especially those stored in partitioned formats like Parquet on S3, understanding and leveraging [partition pruning](https://trino.io/docs/current/admin/dynamic-filtering.html) is critical for optimal performance. Partition pruning is a query optimization technique that allows the query engine to skip reading entire data partitions that are irrelevant to the query's results. This drastically reduces I/O, network traffic, and overall query execution time.

## Trino's Dynamic Filtering for Joins

Trino's powerful Dynamic Filtering feature extends the concept of partition pruning, specifically enabling dynamic partition pruning during query execution, particularly for joins.

When a query involves a join between a filtered "dimension" table (or a table with selective predicates) and a larger "fact" table, Trino can:

Collect relevant values from the filtered side of the join at runtime.

Dynamically push these collected values down as filters to the larger table's scan.

For partitioned tables, this allows Trino to avoid reading unnecessary data files or even entire partitions that do not contain any of the required join key values.

This mechanism is crucial for efficiently processing joins and minimizing data transfer.

## Scenario

Let's illustrate the importance of partition awareness with a common debugging scenario. Imagine a customer has reported higher-than-expected costs for the OCP on GCP flow. You want to identify specific rows where the OCP on Cloud cost for May 2025 is greater than the original GCP cost.


### Data Partitioning Structures

Let's say you are debugging a customer issue where the customer has reported a higher than expected cost for the OCP on GCP flow and you want to find all rows where the ocp on cloud cost is higher for the month of may than the original cost.

Consider our key tables and their partitioning schemas:

GCP Tables:
```
partitioned_by = ARRAY['source','year','month']
```

OCP on GCP Tables:
```
partitioned_by = ARRAY['gcp_source','ocp_source','year','month','day']
```

### Initial Query
```
SELECT
    gcp.row_uuid,
    gcp.unblended_cost AS gcp_unblended_cost,
    ocp_on_gcp.unblended_cost AS ocpgcp_unblended_cost
FROM
    managed_reporting_ocpgcpcostlineitem_project_daily_summary AS ocp_on_gcp
JOIN
    gcp_line_items_daily AS gcp
    ON ocp_on_gcp.row_uuid = gcp.row_uuid
    AND ocp_on_gcp.year = gcp.year
    AND ocp_on_gcp.gcp_source = gcp.source -- Assuming 'source' in gcp maps to 'gcp_source' in ocp_on_gcp
WHERE
    gcp.usage_start >= DATE('2025-05-01')
    AND gcp.usage_start <= DATE('2025-05-31')
    AND gcp.year = '2025'
    AND gcp.source = 'xyz'
    AND gcp.unblended_cost < ocp_on_gcp.unblended_cost;
```

#### Performance Analysis:

During the execution of this query, Trino's optimizer *will* effectively use some pruning:

* **Static Pruning for `source` and `year`:** The predicates `gcp.source = 'xyz'` and `gcp.year = '2025'` will allow Trino to immediately prune the `gcp_line_items_daily` table to only consider data within those specific `source` and `year` partitions.

* **Dynamic Filtering for `gcp_source`/`source` and `year` in Join:** The `ON` clause conditions (`ocp_on_gcp.year = gcp.year` and `ocp_on_gcp.gcp_source = gcp.source`) enable dynamic filtering. This means that once the specific `source` and `year` values are known from the `gcp` side, Trino can dynamically push these filters to the `ocp_on_gcp` table, reducing its scan scope.

**However, a significant optimization opportunity is missed:**

The query *does not* explicitly filter on the `month` or `day` partition columns directly. Instead, it relies on a `usage_start` date range. This means:

* **For `gcp_line_items_daily`:** Even though the query targets May 2025 usage, Trino might still scan **all monthly partitions** within the `source='xyz'` and `year='2025'` directory, and then apply the `usage_start` filter *after* reading the data. This happens because the `month` partition key (`gcp.month`) is not directly constrained in the `WHERE` clause by an equality or range predicate.

* **For `managed_reporting_ocpgcpcostlineitem_project_daily_summary`:** Similarly, even with dynamic filtering for `gcp_source` and `year`, Trino would likely scan **all monthly and daily partitions** within that scope, as `ocp_on_gcp.month` and `ocp_on_gcp.day` are not explicitly filtered in the `WHERE` clause.

This results in Trino reading more data than necessary from S3, increasing I/O and slowing down query execution.

### Maximizing Partition Pruning for Optimal Performance

To fully leverage Trino's partition pruning capabilities, you should always include as many as possible direct filters on the partition columns (`source`, `year`, `month`, `day`) in your `WHERE` clause, in addition to any other specific filtering criteria.

This behavior will avoid scanning any partitions (folders in s3) that do not match the specified month and year leading to:
1. Significantly reduced data scanned from s3
2. Lower I/O costs and network transfer.
3. Faster query execution times.

**Key Takeaway:**
Always ensure your Trino queries include explicit filters on all relevant partition keys in your WHERE clauses to guide the optimizer and maximize partition pruning. Relying solely on filters against non-partitioned columns (like usage_start spanning across months) will lead to unnecessary data scans.

Note: This scenario is continued in the gcp_cross_over_data.md file.
