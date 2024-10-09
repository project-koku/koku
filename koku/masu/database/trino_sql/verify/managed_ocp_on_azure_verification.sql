WITH cte_agg_tags as (
    SELECT array_agg(cte_tag_matches.matched_tag) as matched_tags from (
        SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)
    ) as cte_tag_matches
)
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
    SELECT sum(costinbillingcurrency) AS parquet_total_cost
    FROM hive.{{schema | sqlsafe}}.azure_openshift_daily as parquet_table
    LEFT JOIN cte_agg_tags AS tag_matches
        ON any_match(tag_matches.matched_tags, x->strpos(parquet_table.tags, x) != 0)
        AND parquet_table.resource_id_matched = False
    WHERE parquet_table.source = {{cloud_source_uuid}}
    AND parquet_table.year = {{year}}
    AND parquet_table.month = {{month}}
    AND (resource_id_matched = True or tag_matches.matched_tags IS NOT NULL)
) t2;
