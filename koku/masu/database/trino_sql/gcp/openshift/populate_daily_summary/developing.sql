EXPLAIN ANALYZE SELECT
    gcp.resource_global_name,
    sum(gcp.usage_amount) / 1073741824.0 / (3600 * 24) as capacity
FROM gcp_line_items as gcp
WHERE gcp.resource_global_name
INNER JOIN (
    SELECT temp.resource_global_name as resource_global_name
    FROM managed_gcp_openshift_daily_temp as temp
    WHERE temp.resource_global_name LIKE '%/disk/%'
    AND temp.service_description = 'Compute Engine'
    AND lower(temp.sku_description) LIKE '% pd %'
    AND temp.year = '2025' -- add source & ocp_source
    AND temp.month = '08'
    GROUP BY temp.resource_global_name
) AS ocp_gcp_tmp
    ON ocp_gcp_tmp.resource_global_name = gcp.resource_global_name
WHERE
    month = '08'
    AND year = '2025'
GROUP BY gcp.resource_global_name, date(gcp.usage_start_time);

SELECT
    date(gcp.usage_start_time),
    gcp.resource_global_name,
    sum(gcp.usage_amount) / 1073741824.0 / (3600 * 24) as capacity
FROM gcp_line_items as gcp
WHERE gcp.resource_global_name in (
        SELECT temp.resource_global_name as resource_global_name
        FROM managed_gcp_openshift_daily_temp as temp
        WHERE temp.resource_global_name LIKE '%/disk/%'
        AND temp.service_description = 'Compute Engine'
        AND lower(temp.sku_description) LIKE '% pd %'
        AND temp.year = '2025' -- add source & ocp_source
        AND temp.month = '08'
        GROUP BY temp.resource_global_name
    )
    and month = '08'
    AND year = '2025'
GROUP BY gcp.resource_global_name, date(gcp.usage_start_time);
