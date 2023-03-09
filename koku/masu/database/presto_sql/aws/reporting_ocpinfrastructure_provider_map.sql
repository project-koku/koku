WITH cte_aws_resource_ids AS (
    SELECT DISTINCT
        aws.lineitem_resourceid,
        aws.source
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
    WHERE aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND aws.lineitem_resourceid IS NOT NULL
        AND aws.lineitem_resourceid != ''
        {% if aws_provider_uuid %}
        AND aws.source = '{{aws_provider_uuid | sqlsafe}}'
        {% endif %}
        AND aws.year = '{{year | sqlsafe}}'
        AND aws.month = '{{month | sqlsafe}}'
),

cte_ocp_resource_ids AS (
    SELECT DISTINCT
        ocp.resource_id,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
    AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    AND ocp.resource_id IS NOT NULL
    AND ocp.resource_id != ''
    {% if ocp_provider_uuid %}
    AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
    {% endif %}
    AND ocp.year = '{{year | sqlsafe}}'
    AND ocp.month = '{{month | sqlsafe}}'
)

SELECT DISTINCT
    cte_ocp_resource_ids.source AS ocp_uuid,
    cte_aws_resource_ids.source AS infra_uuid,
    'AWS' AS provider_type
FROM cte_aws_resource_ids
INNER JOIN cte_ocp_resource_ids
    ON strpos(cte_aws_resource_ids.lineitem_resourceid, cte_ocp_resource_ids.resource_id) != 0
;
