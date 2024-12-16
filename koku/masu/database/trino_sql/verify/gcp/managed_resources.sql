WITH cte_agg_tags AS (
    SELECT ARRAY{{matched_tag_array | sqlsafe}} AS matched_tags
),
cte_resource_breakdown AS (
    SELECT
        source_type,
        resource_name,
        usage_start_time,
        SUM(cost) AS cost
    FROM (
        SELECT 'parquet' AS source_type, resource_name, usage_start_time, cost
        FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily parquet_table
        WHERE source = {{cloud_source_uuid}}
        AND year = {{year}} AND month = {{month}}
        AND (ocp_matched = TRUE OR EXISTS (
            SELECT 1
            FROM cte_agg_tags
            WHERE any_match(matched_tags, x -> strpos(parquet_table.labels, x) != 0)
        ))
        UNION ALL
        SELECT 'managed' AS source_type, resource_name, usage_start_time, cost
        FROM hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily
        WHERE source = {{cloud_source_uuid}}
        AND year = {{year}} AND month = {{month}}
        AND (resource_id_matched = TRUE OR matched_tag != '')
    ) aggregated_data
    GROUP BY source_type, resource_name, usage_start_time
),
cte_discrepancies AS (
    SELECT
        p.resource_name,
        p.usage_start_time,
        p.cost AS parquet_cost,
        m.cost AS managed_cost
    FROM cte_resource_breakdown p
    LEFT JOIN cte_resource_breakdown m
        ON p.resource_name = m.resource_name
        AND p.usage_start_time = m.usage_start_time
        AND m.source_type = 'managed'
    WHERE p.source_type = 'parquet'
    AND (COALESCE(m.cost, 0) != p.cost)
),
cte_initial_cost_check AS (
    SELECT
        gcp.resource_name,
        gcp.usage_start_time,
        SUM(gcp.cost) AS initial_cost,
        MAX(d.managed_cost) AS managed_cost,
        MAX(d.parquet_cost) AS parquet_cost,
        CASE
            WHEN SUM(gcp.cost) < MAX(d.parquet_cost) AND SUM(gcp.cost) = MAX(d.managed_cost)
            THEN TRUE ELSE FALSE
        END AS parquet_issue
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily gcp
    JOIN cte_discrepancies d
        ON gcp.resource_name = d.resource_name
        AND gcp.usage_start_time = d.usage_start_time
    WHERE gcp.source = {{cloud_source_uuid}}
    AND gcp.year = {{year}} AND gcp.month = {{month}}
    GROUP BY gcp.resource_name, gcp.usage_start_time
)
SELECT * FROM cte_initial_cost_check where parquet_issue != True LIMIT 40;
