SELECT
    CASE
        WHEN abs(t1.managed_total_cost - t2.parquet_total_cost) < 1 THEN true
        ELSE false
    END AS counts_match
FROM
(
    SELECT sum(pretax_cost) AS managed_total_cost
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary as managed_ocpcloud
    WHERE managed_ocpcloud.source = {{cloud_provider_uuid}}
    AND managed_ocpcloud.year = {{year}}
    AND managed_ocpcloud.month = {{month}}
) t1,
(
    SELECT sum(pretax_cost) AS parquet_total_cost
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary as ocpcloud
    WHERE ocpcloud.azure_source = {{cloud_provider_uuid}}
    AND ocpcloud.year = {{year}}
    AND ocpcloud.month = {{month}}
) t2;
