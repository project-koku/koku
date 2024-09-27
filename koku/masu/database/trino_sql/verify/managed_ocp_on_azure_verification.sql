SELECT
    CASE
        WHEN abs(t1.managed_total_cost - t2.parquet_total_cost) < 1 THEN true
        ELSE false
    END AS counts_match
FROM
(
    SELECT sum(costinbillingcurrency) AS managed_total_cost
    FROM hive.{{schema | sqlsafe}}.managed_azure_openshift_daily as managed_ocpcloud
    WHERE managed_ocpcloud.source = {{cloud_source_uuid}}
    AND managed_ocpcloud.year = {{year}}
    AND managed_ocpcloud.month = {{month}}
    AND (resource_id_matched = True or matched_tag != '')
) t1,
(
    SELECT sum(pretax_cost) AS parquet_total_cost
    FROM hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary as parquet_table
    WHERE parquet_table.azure_source = {{cloud_source_uuid}}
    AND parquet_table.year = {{year}}
    AND lpad(parquet_table.month, 2, '0') = {{month}}
) t2;
