INSERT INTO hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_openshift_daily (
    invoice_month,
    billing_account_id,
    project_id,
    usage_start_time,
    service_id,
    sku_id,
    system_labels,
    labels,
    cost_type,
    location_region,
    resource_name,
    project_name,
    service_description,
    sku_description,
    usage_pricing_unit,
    usage_amount_in_pricing_units,
    currency,
    cost,
    daily_credits,
    resource_global_name,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
SELECT ranked.invoice_month,
    ranked.billing_account_id,
    ranked.project_id,
    ranked.usage_start_time,
    ranked.service_id,
    ranked.sku_id,
    ranked.system_labels,
    ranked.labels,
    ranked.cost_type,
    ranked.location_region,
    ranked.resource_name,
    ranked.project_name,
    ranked.service_description,
    ranked.sku_description,
    ranked.usage_pricing_unit,
    ranked.usage_amount_in_pricing_units,
    ranked.currency,
    ranked.cost,
    ranked.daily_credits,
    ranked.resource_global_name,
    ranked.resource_id_matched,
    ranked.matched_tag,
    ranked.source as source,
    ranked.ocp_source as ocp_source,
    ranked.year,
    ranked.month,
    cast(day(ranked.usage_start_time) as varchar) as day
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY row_uuid ORDER BY usage_amount_in_pricing_units) AS row_number
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp AS gcp
    WHERE gcp.source = {{cloud_provider_uuid}}
        AND gcp.year = {{year}}
        AND gcp.month = {{month}}
        AND gcp.usage_start_time >= {{start_date}}
        AND gcp.usage_start_time < DATE_ADD('day', 1, {{end_date}})
        AND gcp.ocp_source IN {{ocp_provider_uuids | inclause}}
) ranked
WHERE row_number = 1;
