-- reporting_ocp_cost_breakdown_p.sql (Phase 4 PoC)
--
-- Populates OCPCostUIBreakDownP from two sources:
--   1. rates_to_usage     — per-rate leaf nodes
--   2. reporting_ocpusagelineitem_daily_summary — distribution rows only
--
-- IQ-4: build_path() and build_path_distributed() are implemented as
-- CASE/WHEN expressions, following koku's standard SQL pattern.
--
-- Tree structure (from data-model.md):
--   depth 1: total_cost
--   depth 2: {top_category}                              e.g. "project", "overhead"
--   depth 3: {top_category}.{breakdown_category}         e.g. "project.usage_cost"
--             or {top_category}.{distribution_type}       e.g. "overhead.platform_distributed"
--   depth 4: {top_category}.{breakdown_category}.{name}  e.g. "project.usage_cost.OpenShift_Subscriptions"
--             or {overhead}.{dist_type}.{breakdown_cat}   e.g. "overhead.platform_distributed.usage_cost"
--   depth 5: overhead.{dist_type}.{brkdn_cat}.{name}     e.g. "overhead.platform_distributed.usage_cost.OpenShift_Sub"
--
-- Parameters:
--   schema, start_date, end_date, source_uuid
--
-- This file contains multiple statements (DELETE + 3 INSERTs).
-- Execute with _execute_processing_script or cursor.execute().

-- Step 0: Clear existing breakdown rows for the recalculation window
DELETE FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND source_uuid = {{source_uuid}}
;

-- Step 1: Insert leaf rows from both sources
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_type, cost_value, distributed_cost,
    path, depth, parent_path, top_category, breakdown_category
)

-- Source 1: Per-rate leaf rows from RatesToUsage (depth 4 for project, depth 4 for overhead per-rate)
SELECT
    uuid_generate_v4(),
    r.usage_start,
    r.usage_end,
    r.source_uuid::uuid,
    r.cluster_id,
    r.cluster_alias,
    r.namespace,
    r.node,
    r.cost_category_id,
    r.custom_name,
    r.metric_type,
    r.cost_model_rate_type,
    r.cost_model_rate_type AS cost_type,   -- "Infrastructure" or "Supplementary"

    r.calculated_cost AS cost_value,
    NULL AS distributed_cost,

    -- build_path(): top_category.breakdown_category.custom_name
    CASE
        WHEN r.cost_category_id IS NULL OR cc.name != 'Platform'
        THEN 'project.'
             || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                     ELSE 'usage_cost'
                END
             || '.' || r.custom_name
        ELSE 'overhead.'
             || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                     ELSE 'usage_cost'
                END
             || '.' || r.custom_name
    END AS path,

    4 AS depth,

    -- parent_path: top_category.breakdown_category
    CASE
        WHEN r.cost_category_id IS NULL OR cc.name != 'Platform'
        THEN 'project.'
             || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                     ELSE 'usage_cost'
                END
        ELSE 'overhead.'
             || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                     ELSE 'usage_cost'
                END
    END AS parent_path,

    -- top_category
    CASE
        WHEN r.cost_category_id IS NULL OR cc.name != 'Platform' THEN 'project'
        ELSE 'overhead'
    END AS top_category,

    -- breakdown_category
    CASE
        WHEN r.metric_type = 'markup' THEN 'markup'
        ELSE 'usage_cost'
    END AS breakdown_category

FROM {{schema | sqlsafe}}.rates_to_usage r
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cc
    ON r.cost_category_id = cc.id
WHERE r.usage_start >= {{start_date}}
    AND r.usage_start <= {{end_date}}
    AND r.source_uuid = {{source_uuid}}

UNION ALL

-- Source 2: Distribution leaf rows from daily summary
-- These are at depth 3 under the overhead branch
-- (overhead.{distribution_type}) with distributed_cost
SELECT
    uuid_generate_v4(),
    lids.usage_start,
    lids.usage_end,
    lids.source_uuid,
    lids.cluster_id,
    lids.cluster_alias,
    lids.namespace,
    lids.node,
    lids.cost_category_id,
    lids.cost_model_rate_type AS custom_name,
    'distributed' AS metric_type,
    lids.cost_model_rate_type,
    NULL AS cost_type,                       -- IQ-8: NULL for distribution rows

    NULL AS cost_value,
    lids.distributed_cost,

    -- build_path_distributed(): overhead.{distribution_type}
    'overhead.' || lids.cost_model_rate_type AS path,

    3 AS depth,

    -- parent_path: overhead
    'overhead' AS parent_path,

    'overhead' AS top_category,

    lids.cost_model_rate_type AS breakdown_category

FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
WHERE lids.usage_start >= {{start_date}}
    AND lids.usage_start <= {{end_date}}
    AND lids.source_uuid = {{source_uuid}}
    AND lids.cost_model_rate_type IN (
        'platform_distributed', 'worker_distributed',
        'unattributed_storage', 'unattributed_network', 'gpu_distributed'
    )
    AND lids.distributed_cost IS NOT NULL
    AND lids.distributed_cost != 0
;

-- Step 2: Insert intermediate nodes at depth 3
-- Aggregate leaf rows (depth 4) by top_category + breakdown_category
-- Distribution rows (depth 3 from Source 2) are already at depth 3,
-- so we only aggregate the depth 4 per-rate leaves here.
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_type, cost_value, distributed_cost,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    max(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    max(b.cluster_alias),
    NULL AS namespace,
    NULL AS node,
    NULL AS cost_category_id,
    b.breakdown_category AS custom_name,
    'aggregate' AS metric_type,
    NULL AS cost_model_rate_type,
    NULL AS cost_type,
    SUM(b.cost_value) AS cost_value,
    SUM(b.distributed_cost) AS distributed_cost,

    b.top_category || '.' || b.breakdown_category AS path,

    3 AS depth,

    b.top_category AS parent_path,

    b.top_category,
    b.breakdown_category

FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}
    AND b.usage_start <= {{end_date}}
    AND b.source_uuid = {{source_uuid}}
    AND b.depth = 4
GROUP BY
    b.usage_start,
    b.source_uuid,
    b.cluster_id,
    b.top_category,
    b.breakdown_category
;

-- Step 3: Insert intermediate nodes at depth 2
-- Aggregate depth 3 nodes by top_category
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_type, cost_value, distributed_cost,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    max(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    max(b.cluster_alias),
    NULL AS namespace,
    NULL AS node,
    NULL AS cost_category_id,
    b.top_category AS custom_name,
    'aggregate' AS metric_type,
    NULL AS cost_model_rate_type,
    NULL AS cost_type,
    SUM(b.cost_value) AS cost_value,
    SUM(b.distributed_cost) AS distributed_cost,

    b.top_category AS path,

    2 AS depth,

    'total_cost' AS parent_path,

    b.top_category,
    'total' AS breakdown_category

FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}
    AND b.usage_start <= {{end_date}}
    AND b.source_uuid = {{source_uuid}}
    AND b.depth = 3
GROUP BY
    b.usage_start,
    b.source_uuid,
    b.cluster_id,
    b.top_category
;

-- Step 4: Insert root node at depth 1 (total_cost)
-- Aggregate depth 2 nodes
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_type, cost_value, distributed_cost,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    max(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    max(b.cluster_alias),
    NULL AS namespace,
    NULL AS node,
    NULL AS cost_category_id,
    'total_cost' AS custom_name,
    'aggregate' AS metric_type,
    NULL AS cost_model_rate_type,
    NULL AS cost_type,
    SUM(b.cost_value) AS cost_value,
    SUM(b.distributed_cost) AS distributed_cost,

    'total_cost' AS path,

    1 AS depth,

    '' AS parent_path,

    'total' AS top_category,
    'total' AS breakdown_category

FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}
    AND b.usage_start <= {{end_date}}
    AND b.source_uuid = {{source_uuid}}
    AND b.depth = 2
GROUP BY
    b.usage_start,
    b.source_uuid,
    b.cluster_id
;
