-- reporting_ocp_cost_breakdown_p.sql (Phase 4)
--
-- Populates OCPCostUIBreakDownP from a single source: rates_to_usage.
-- Per-rate usage costs become project leaves (depth 4).
-- Per-rate distributed costs become overhead leaves (depth 5).
-- Intermediate nodes (depth 3, 2, 1) are bottom-up aggregations.
--
-- The tree is rooted per-cluster (one total_cost node per cluster_id per day).
-- Multi-cluster sources produce multiple roots; the API aggregates as needed.
--
-- Parameters: schema, start_date, end_date, source_uuid

-- Step 0: Clear existing breakdown rows for the recalculation window
DELETE FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}::uuid
;

-- Step 1: Depth 4 -- project per-rate leaves (usage costs from RTU)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    r.usage_start,
    r.usage_start,
    r.source_uuid::uuid,
    r.cluster_id,
    MAX(r.cluster_alias),
    r.namespace,
    r.node,
    MAX(r.cost_category_id),
    r.custom_name,
    r.metric_type,
    r.cost_model_rate_type,
    SUM(r.calculated_cost),
    NULL,
    (SELECT MAX(raw_currency) FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
     WHERE source_uuid = {{source_uuid}}::uuid
       AND usage_start >= {{start_date}}::date
       AND usage_start <= {{end_date}}::date
       AND raw_currency IS NOT NULL),
    'project.' || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                       ELSE 'usage_cost'
                  END || '.' || r.custom_name,
    4,
    'project.' || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                       ELSE 'usage_cost'
                  END,
    'project',
    CASE WHEN r.metric_type = 'markup' THEN 'markup' ELSE 'usage_cost' END
FROM {{schema | sqlsafe}}.rates_to_usage r
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cc
    ON r.cost_category_id = cc.id
WHERE r.usage_start >= {{start_date}}::date
    AND r.usage_start <= {{end_date}}::date
    AND r.source_uuid = {{source_uuid}}::uuid
    AND r.monthly_cost_type IS NULL
    AND (r.cost_category_id IS NULL OR cc.name != 'Platform')
    AND r.namespace NOT IN ('Worker unallocated', 'Storage unattributed', 'Network unattributed', 'GPU unallocated')
GROUP BY r.usage_start, r.source_uuid, r.cluster_id,
         r.namespace, r.node, r.custom_name, r.metric_type, r.cost_model_rate_type
HAVING SUM(r.calculated_cost) != 0
;

-- Step 2: Depth 5 -- overhead per-rate distribution leaves
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    r.usage_start,
    r.usage_start,
    r.source_uuid::uuid,
    r.cluster_id,
    MAX(r.cluster_alias),
    r.namespace,
    r.node,
    MAX(r.cost_category_id),
    r.custom_name,
    r.metric_type,
    r.cost_model_rate_type,
    NULL,
    SUM(r.distributed_cost),
    (SELECT MAX(raw_currency) FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
     WHERE source_uuid = {{source_uuid}}::uuid
       AND usage_start >= {{start_date}}::date
       AND usage_start <= {{end_date}}::date
       AND raw_currency IS NOT NULL),
    'overhead.' || r.monthly_cost_type
        || '.' || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                       WHEN r.cost_model_rate_type = 'Infrastructure' THEN 'infrastructure'
                       ELSE 'usage_cost' END
        || '.' || r.custom_name,
    5,
    'overhead.' || r.monthly_cost_type
        || '.' || CASE WHEN r.metric_type = 'markup' THEN 'markup'
                       WHEN r.cost_model_rate_type = 'Infrastructure' THEN 'infrastructure'
                       ELSE 'usage_cost' END,
    'overhead',
    CASE WHEN r.metric_type = 'markup' THEN 'markup'
         WHEN r.cost_model_rate_type = 'Infrastructure' THEN 'infrastructure'
         ELSE 'usage_cost' END
FROM {{schema | sqlsafe}}.rates_to_usage r
WHERE r.usage_start >= {{start_date}}::date
    AND r.usage_start <= {{end_date}}::date
    AND r.source_uuid = {{source_uuid}}::uuid
    AND r.monthly_cost_type IS NOT NULL
    AND r.distributed_cost IS NOT NULL
    AND r.distributed_cost != 0
GROUP BY r.usage_start, r.source_uuid, r.cluster_id,
         r.namespace, r.node, r.custom_name, r.metric_type,
         r.cost_model_rate_type, r.monthly_cost_type
;

-- Step 3: Depth 4 -- aggregate depth 5 overhead leaves by distribution type + breakdown category
-- parent_path of depth 5 = overhead.{dist_type}.{breakdown_cat} which becomes the depth 4 path.
-- The depth 4 parent_path = overhead.{dist_type} = first two segments of the depth 5 parent_path.
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    MAX(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    MAX(b.cluster_alias),
    NULL, NULL, NULL,
    b.breakdown_category,
    'aggregate',
    NULL, NULL,
    SUM(b.distributed_cost),
    MAX(b.raw_currency),
    b.parent_path,
    4,
    SPLIT_PART(b.parent_path, '.', 1) || '.' || SPLIT_PART(b.parent_path, '.', 2),
    'overhead',
    b.breakdown_category
FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}::date
    AND b.usage_start <= {{end_date}}::date
    AND b.source_uuid = {{source_uuid}}::uuid
    AND b.depth = 5
GROUP BY b.usage_start, b.source_uuid, b.cluster_id,
         b.parent_path, b.breakdown_category
;

-- Step 4: Depth 3 -- aggregate depth 4 by top_category + breakdown_category (project)
-- and by distribution type (overhead)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    MAX(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    MAX(b.cluster_alias),
    NULL, NULL, NULL,
    SPLIT_PART(b.parent_path, '.', 2),
    'aggregate',
    NULL,
    SUM(b.cost_value),
    SUM(b.distributed_cost),
    MAX(b.raw_currency),
    b.parent_path,
    3,
    b.top_category,
    b.top_category,
    SPLIT_PART(b.parent_path, '.', 2)
FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}::date
    AND b.usage_start <= {{end_date}}::date
    AND b.source_uuid = {{source_uuid}}::uuid
    AND b.depth = 4
GROUP BY b.usage_start, b.source_uuid, b.cluster_id,
         b.top_category, b.parent_path
;

-- Step 5: Depth 2 -- aggregate depth 3 by top_category
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    MAX(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    MAX(b.cluster_alias),
    NULL, NULL, NULL,
    b.top_category,
    'aggregate',
    NULL,
    SUM(b.cost_value),
    SUM(b.distributed_cost),
    MAX(b.raw_currency),
    b.top_category,
    2,
    'total_cost',
    b.top_category,
    'total'
FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}::date
    AND b.usage_start <= {{end_date}}::date
    AND b.source_uuid = {{source_uuid}}::uuid
    AND b.depth = 3
GROUP BY b.usage_start, b.source_uuid, b.cluster_id, b.top_category
;

-- Step 6: Depth 1 -- total_cost root node (one per cluster per day).
-- Multi-cluster providers produce one root per cluster_id; the API layer
-- aggregates across clusters when no group_by[cluster] is specified.
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p (
    id, usage_start, usage_end, source_uuid, cluster_id, cluster_alias,
    namespace, node, cost_category_id, custom_name, metric_type,
    cost_model_rate_type, cost_value, distributed_cost, raw_currency,
    path, depth, parent_path, top_category, breakdown_category
)
SELECT
    uuid_generate_v4(),
    b.usage_start,
    MAX(b.usage_end),
    b.source_uuid,
    b.cluster_id,
    MAX(b.cluster_alias),
    NULL, NULL, NULL,
    'total_cost',
    'aggregate',
    NULL,
    SUM(b.cost_value),
    SUM(b.distributed_cost),
    MAX(b.raw_currency),
    'total_cost',
    1,
    '',
    'total',
    'total'
FROM {{schema | sqlsafe}}.reporting_ocp_cost_breakdown_p b
WHERE b.usage_start >= {{start_date}}::date
    AND b.usage_start <= {{end_date}}::date
    AND b.source_uuid = {{source_uuid}}::uuid
    AND b.depth = 2
GROUP BY b.usage_start, b.source_uuid, b.cluster_id
;
