-- The Python Jinja string variable subsitutions aws_where_clause and ocp_where_clause
-- optionally filter AWS and OCP data by provider/source
-- Ex aws_where_clause: 'AND cost_entry_bill_id IN (1, 2, 3)'
-- Ex ocp_where_clause: "AND cluster_id = 'abcd-1234`"
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} AS (
    WITH cte_unnested_aws_tags AS (
        SELECT tags.*,
            b.billing_period_start
        FROM (
            SELECT key,
                value,
                cost_entry_bill_id
            FROM postgres.{{schema | sqlsafe}}.reporting_awstags_summary AS ts
            CROSS JOIN UNNEST("values") AS v(value)
        ) AS tags
        JOIN postgres.{{schema | sqlsafe}}.reporting_awscostentrybill AS b
            ON tags.cost_entry_bill_id = b.id
        JOIN postgres.{{schema | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        WHERE b.id = {{bill_id}}
    ),
    cte_unnested_ocp_pod_tags AS (
        SELECT tags.*,
            rp.report_period_start,
            rp.cluster_id,
            rp.cluster_alias
        FROM (
            SELECT key,
                value,
                report_period_id
            FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ts
            CROSS JOIN UNNEST("values") AS v(value)
        ) AS tags
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
            ON tags.report_period_id = rp.id
        -- Filter out tags that aren't enabled
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        WHERE rp.cluster_id = {{cluster_id}}
    ),
    cte_unnested_ocp_volume_tags AS (
        SELECT tags.*,
            rp.report_period_start,
            rp.cluster_id,
            rp.cluster_alias
        FROM (
            SELECT key,
                value,
                report_period_id
            FROM postgres.{{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ts
            CROSS JOIN UNNEST("values") AS v(value)
        ) AS tags
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
            ON tags.report_period_id = rp.id
        -- Filter out tags that aren't enabled
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        WHERE rp.cluster_id = {{cluster_id}}
    )
    SELECT '{"' || key || '": "' || value || '"}' as tag,
        key,
        value,
        cost_entry_bill_id,
        report_period_id
    FROM (
        SELECT aws.key,
            aws.value,
            aws.cost_entry_bill_id,
            ocp.report_period_id
        FROM cte_unnested_aws_tags AS aws
        JOIN cte_unnested_ocp_pod_tags AS ocp
            ON lower(aws.key) = lower(ocp.key)
                AND lower(aws.value) = lower(ocp.value)
                AND aws.billing_period_start = ocp.report_period_start

        UNION

        SELECT aws.key,
            aws.value,
            aws.cost_entry_bill_id,
            ocp.report_period_id
        FROM cte_unnested_aws_tags AS aws
        JOIN cte_unnested_ocp_volume_tags AS ocp
            ON lower(aws.key) = lower(ocp.key)
                AND lower(aws.value) = lower(ocp.value)
                AND aws.billing_period_start = ocp.report_period_start
    ) AS matches
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}} AS (
    SELECT {{bill_id | sqlsafe}} as cost_entry_bill_id,
        cast(uuid() as varchar) as line_item_id,
        resource_id,
        usage_start,
        usage_end,
        product_code,
        product_family,
        instance_type,
        usage_account_id,
        availability_zone,
        region,
        unit,
        sum(usage_amount) as usage_amount,
        sum(normalized_usage_amount) as normalized_usage_amount,
        currency_code,
        sum(unblended_cost) as unblended_cost,
        tags,
        max(lower_tags) as lower_tags
    FROM (
        SELECT aws.lineitem_resourceid as resource_id,
            date(aws.lineitem_usagestartdate) as usage_start,
            date(aws.lineitem_usagestartdate) as usage_end,
            aws.lineitem_productcode as product_code,
            aws.product_productfamily as product_family,
            aws.product_instancetype as instance_type,
            aws.lineitem_usageaccountid as usage_account_id,
            aws.lineitem_availabilityzone as availability_zone,
            aws.product_region as region,
            aws.pricing_unit as unit,
            aws.lineitem_usageamount as usage_amount,
            aws.lineitem_normalizedusageamount as normalized_usage_amount,
            aws.lineitem_currencycode as currency_code,
            aws.lineitem_unblendedcost as unblended_cost,
            resourcetags as tags,
            lower(aws.resourcetags) as lower_tags
        FROM hive.{{schema | sqlsafe}}.aws_line_items as aws
        WHERE aws.source = '{{aws_source_uuid | sqlsafe}}'
            AND aws.year = '{{year | sqlsafe}}'
            AND aws.month = '{{month | sqlsafe}}'
            AND date(aws.lineitem_usagestartdate) >= date('{{start_date | sqlsafe}}')
            AND date(aws.lineitem_usagestartdate) <= date('{{end_date | sqlsafe}}')
    )
    GROUP BY resource_id,
        usage_start,
        usage_end,
        product_code,
        product_family,
        instance_type,
        usage_account_id,
        availability_zone,
        region,
        unit,
        currency_code,
        tags

)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_aws_tags_{{uuid | sqlsafe}} AS (
    SELECT aws.*
    FROM (
        SELECT aws.*,
            row_number() OVER (PARTITION BY aws.line_item_id ORDER BY aws.line_item_id) as row_number
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}} as aws
        JOIN hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} as tag
            ON json_extract_scalar(aws.tags, '$.' || tag.key) = tag.value
    ) AS aws
    WHERE aws.row_number = 1
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} AS (
    SELECT aws.*
    FROM hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}} as aws
    WHERE (
        strpos(lower_tags, 'openshift_cluster') != 0
        OR strpos(lower_tags, 'openshift_node') != 0
        OR strpos(lower_tags, 'openshift_project') != 0
    )
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}} AS (
    SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
        ocp.usage_start,
        ocp.report_period_id,
        ocp.cluster_id,
        ocp.cluster_alias,
        ocp.namespace,
        ocp.node,
        ocp.persistentvolumeclaim,
        ocp.persistentvolume,
        ocp.storageclass,
        ocp.persistentvolumeclaim_capacity_gigabyte,
        ocp.persistentvolumeclaim_capacity_gigabyte_months,
        ocp.volume_request_storage_gigabyte_months,
        ocp.persistentvolumeclaim_usage_gigabyte_months,
        json_format(ocp.volume_labels) as volume_labels,
        lower(tag.key) as key,
        lower(tag.value) as value,
        lower(tag.tag) as tag
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} AS tag
        ON ocp.report_period_id = tag.report_period_id
        AND json_extract_scalar(ocp.volume_labels, '$.' || tag.key) = tag.value
    WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
        AND ocp.data_source = 'Storage'
        AND date(ocp.usage_start) >= date('{{start_date | sqlsafe}}')
        AND date(ocp.usage_start) <= date('{{end_date | sqlsafe}}')
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}} AS (
    SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
        ocp.usage_start,
        ocp.report_period_id,
        ocp.cluster_id,
        ocp.cluster_alias,
        ocp.namespace,
        ocp.node,
        json_format(ocp.pod_labels) as pod_labels,
        ocp.pod_usage_cpu_core_hours,
        ocp.pod_request_cpu_core_hours,
        ocp.pod_limit_cpu_core_hours,
        ocp.pod_usage_memory_gigabyte_hours,
        ocp.pod_request_memory_gigabyte_hours,
        ocp.node_capacity_cpu_cores,
        ocp.node_capacity_cpu_core_hours,
        ocp.node_capacity_memory_gigabytes,
        ocp.node_capacity_memory_gigabyte_hours,
        ocp.cluster_capacity_cpu_core_hours,
        ocp.cluster_capacity_memory_gigabyte_hours,
        lower(tag.key) as key,
        lower(tag.value) as value,
        lower(tag.tag) as tag
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} AS tag
        ON ocp.report_period_id = tag.report_period_id
        AND json_extract_scalar(ocp.pod_labels, '$.' || tag.key) = tag.value
    WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
        AND ocp.data_source = 'Pod'
        AND date(ocp.usage_start) >= date('{{start_date | sqlsafe}}')
        AND date(ocp.usage_start) <= date('{{end_date | sqlsafe}}')
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}};


-- First we match OCP pod data to AWS data using a direct
-- resource id match. This usually means OCP node -> AWS EC2 instance ID.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS (
    WITH cte_resource_id_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            json_format(ocp.pod_labels) as pod_labels,
            ocp.pod_usage_cpu_core_hours,
            ocp.pod_request_cpu_core_hours,
            ocp.pod_limit_cpu_core_hours,
            ocp.pod_usage_memory_gigabyte_hours,
            ocp.pod_request_memory_gigabyte_hours,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_hours,
            ocp.node_capacity_memory_gigabytes,
            ocp.node_capacity_memory_gigabyte_hours,
            ocp.cluster_capacity_cpu_core_hours,
            ocp.cluster_capacity_memory_gigabyte_hours,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.resource_id = ocp.resource_id
                AND aws.usage_start = ocp.usage_start
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
            AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
            AND ocp.data_source = 'Pod'
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_resource_id_matched
        GROUP BY aws_id
    )
    SELECT rm.*,
        (rm.pod_usage_cpu_core_hours / rm.node_capacity_cpu_core_hours) * rm.unblended_cost as project_cost,
        shared.shared_projects
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared AS shared
        ON rm.aws_id = shared.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_project key
-- and the value matches an OpenShift project name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            json_format(ocp.pod_labels) as pod_labels,
            ocp.pod_usage_cpu_core_hours,
            ocp.pod_request_cpu_core_hours,
            ocp.pod_limit_cpu_core_hours,
            ocp.pod_usage_memory_gigabyte_hours,
            ocp.pod_request_memory_gigabyte_hours,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_hours,
            ocp.node_capacity_memory_gigabytes,
            ocp.node_capacity_memory_gigabyte_hours,
            ocp.cluster_capacity_cpu_core_hours,
            ocp.cluster_capacity_memory_gigabyte_hours,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_project') = lower(ocp.namespace)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
;

-- Next we match where the AWS tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            json_format(ocp.pod_labels) as pod_labels,
            ocp.pod_usage_cpu_core_hours,
            ocp.pod_request_cpu_core_hours,
            ocp.pod_limit_cpu_core_hours,
            ocp.pod_usage_memory_gigabyte_hours,
            ocp.pod_request_memory_gigabyte_hours,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_hours,
            ocp.node_capacity_memory_gigabytes,
            ocp.node_capacity_memory_gigabyte_hours,
            ocp.cluster_capacity_cpu_core_hours,
            ocp.cluster_capacity_memory_gigabyte_hours,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_node') = lower(ocp.node)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            json_format(ocp.pod_labels) as pod_labels,
            ocp.pod_usage_cpu_core_hours,
            ocp.pod_request_cpu_core_hours,
            ocp.pod_limit_cpu_core_hours,
            ocp.pod_usage_memory_gigabyte_hours,
            ocp.pod_request_memory_gigabyte_hours,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_hours,
            ocp.node_capacity_memory_gigabytes,
            ocp.node_capacity_memory_gigabyte_hours,
            ocp.cluster_capacity_cpu_core_hours,
            ocp.cluster_capacity_memory_gigabyte_hours,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
;

-- Next we match where the pod label key and value
-- and AWS tag key and value match directly
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT ocp.ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_hours,
            ocp.pod_request_cpu_core_hours,
            ocp.pod_limit_cpu_core_hours,
            ocp.pod_usage_memory_gigabyte_hours,
            ocp.pod_request_memory_gigabyte_hours,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_hours,
            ocp.node_capacity_memory_gigabytes,
            ocp.node_capacity_memory_gigabyte_hours,
            ocp.cluster_capacity_cpu_core_hours,
            ocp.cluster_capacity_memory_gigabyte_hours,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_tags_{{uuid | sqlsafe}} as aws
        JOIN hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON aws.usage_start = ocp.usage_start
                AND strpos(aws.lower_tags, ocp.tag) != 0
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_daily_{{uuid | sqlsafe}};
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}};


-- First we match where the AWS tag is the special openshift_project key
-- and the value matches an OpenShift project name
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_gigabyte,
            ocp.persistentvolumeclaim_capacity_gigabyte_months,
            ocp.volume_request_storage_gigabyte_months,
            ocp.persistentvolumeclaim_usage_gigabyte_months,
            json_format(ocp.volume_labels) as volume_labels,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_project') = lower(ocp.namespace)
                AND aws.usage_start = ocp.usage_start
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
            AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_gigabyte,
            ocp.persistentvolumeclaim_capacity_gigabyte_months,
            ocp.volume_request_storage_gigabyte_months,
            ocp.persistentvolumeclaim_usage_gigabyte_months,
            json_format(ocp.volume_labels) as volume_labels,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_node') = lower(ocp.node)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT cast(ocp.uuid AS VARCHAR) AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_gigabyte,
            ocp.persistentvolumeclaim_capacity_gigabyte_months,
            ocp.volume_request_storage_gigabyte_months,
            ocp.persistentvolumeclaim_usage_gigabyte_months,
            json_format(ocp.volume_labels) as volume_labels,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(aws.lower_tags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id

;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_special_case_tags_{{uuid | sqlsafe}}
;


-- Then we match for OpenShift volume data where the volume label key and value
-- and AWS tag key and value match directly
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}}
    WITH cte_tag_matched AS (
        SELECT ocp.ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_gigabyte,
            ocp.persistentvolumeclaim_capacity_gigabyte_months,
            ocp.volume_request_storage_gigabyte_months,
            ocp.persistentvolumeclaim_usage_gigabyte_months,
            ocp.volume_labels,
            aws.cost_entry_bill_id,
            aws.line_item_id as aws_id,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.usage_account_id,
            aws.availability_zone,
            aws.region,
            aws.unit,
            aws.usage_amount,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_cost,
            aws.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_aws_tags_{{uuid | sqlsafe}} as aws
        JOIN hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON aws.usage_start = ocp.usage_start
                AND strpos(aws.lower_tags, ocp.tag) != 0
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.line_item_id
        WHERE rm.aws_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.aws_id = shared.aws_id

;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_aws_tags_{{uuid | sqlsafe}}
;


-- The full summary data for Openshift pod<->AWS and
-- Openshift volume<->AWS matches are UNIONed together
-- with a GROUP BY using the AWS ID to deduplicate
-- the AWS data. This should ensure that we never double count
-- AWS cost or usage.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_pod_project_cost AS (
        SELECT pc.aws_id,
            map_agg(pc.namespace, pc.project_cost) as project_costs
            FROM (
                SELECT li.aws_id,
                    li.namespace,
                    sum(project_cost) as project_cost
                FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} as li
                GROUP BY li.aws_id, li.namespace
            ) AS pc
        GROUP BY pc.aws_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.aws_id,
            map_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.aws_id, li.namespace
        ) AS pc
        GROUP BY pc.aws_id
    )
    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        max(li.resource_id) as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(li.product_family) as product_family,
        max(li.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(li.region) as region,
        max(li.unit) as unit,
        li.tags,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_cost) as unblended_cost,
        max(li.unblended_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        '{{aws_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN cte_pod_project_cost as pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    -- Dedup on AWS line item so we never double count usage or cost
    GROUP BY li.aws_id, li.tags, pc.project_costs

    UNION

    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        max(li.resource_id) as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(li.product_family) as product_family,
        max(li.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(li.region) as region,
        max(li.unit) as unit,
        li.tags,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_cost) as unblended_cost,
        max(li.unblended_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs,
        '{{aws_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS li
    JOIN cte_storage_project_cost AS pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.aws_id = li.aws_id
        AND ulid.aws_id IS NULL
    GROUP BY li.aws_id, li.tags, pc.project_costs
)
;

-- The full summary data for Openshift pod<->AWS and
-- Openshift volume<->AWS matches are UNIONed together
-- with a GROUP BY using the OCP ID to deduplicate
-- based on OpenShift data. This is effectively the same table
-- as reporting_ocpawscostlineitem_daily_summary but from the OpenShift
-- point of view. Here usage and cost are divided by the
-- number of pods sharing the cost so the values turn out the
-- same when reported.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        'Pod' as data_source,
        li.namespace,
        li.node,
        li.pod_labels,
        max(li.resource_id) as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(li.product_family) as product_family,
        max(li.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(li.region) as region,
        max(li.unit) as unit,
        sum(li.usage_amount / li.shared_projects) as usage_amount,
        sum(li.normalized_usage_amount / li.shared_projects) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        sum(li.unblended_cost / li.shared_projects) as unblended_cost,
        sum(li.unblended_cost / li.shared_projects) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        li.project_cost,
        li.project_cost * cast({{markup}} as decimal(24,9)) as project_markup_cost,
        '{{aws_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} as li
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    -- Grouping by OCP this time for the by project view
    GROUP BY li.report_period_id,
        li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.pod_labels,
        li.project_cost

    UNION

    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        'Storage' as data_source,
        li.namespace,
        li.node,
        li.volume_labels as pod_labels,
        NULL as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(li.product_family) as product_family,
        max(li.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(li.region) as region,
        max(li.unit) as unit,
        sum(li.usage_amount / li.shared_projects) as usage_amount,
        sum(li.normalized_usage_amount / li.shared_projects) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        sum(li.unblended_cost / li.shared_projects) as unblended_cost,
        sum(li.unblended_cost / li.shared_projects) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        li.project_cost,
        li.project_cost * cast({{markup}} as decimal(24,9)) as project_markup_cost,
        '{{aws_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS li
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.aws_id = li.aws_id
    WHERE ulid.aws_id IS NULL
    GROUP BY li.ocp_id,
        li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.volume_labels,
        li.project_cost
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}};

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}};


-- Clear out old entries first
INSERT
  INTO postgres.{{schema | sqlsafe}}.presto_delete_wrapper_log
       (
           id,
           action_ts,
           table_name,
           where_clause,
           result_rows
       )
VALUES (
    uuid(),
    now(),
    'reporting_ocpawscostlineitem_daily_summary',
    'WHERE usage_start >= '{{start_date}}'::date ' ||
      'AND usage_start <= '{{end_date}}'::date ' ||
      'AND cluster_id = '{{cluster_id}}' ' ||
      'AND cost_entry_bill_id = {{bill_id}} ',
    null
)
;

-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    resource_id,
    usage_start,
    usage_end,
    product_code,
    product_family,
    instance_type,
    cost_entry_bill_id,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    tags,
    usage_amount,
    normalized_usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    shared_projects,
    project_costs,
    source_uuid
)
    SELECT uuid(),
        report_period_id,
        cluster_id,
        cluster_alias,
        namespace,
        node,
        resource_id,
        usage_start,
        usage_end,
        product_code,
        product_family,
        instance_type,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        availability_zone,
        region,
        unit,
        json_parse(tags),
        cast(usage_amount AS decimal(24,9)),
        normalized_usage_amount,
        currency_code,
        cast(unblended_cost AS decimal(30,15)),
        cast(markup_cost  AS decimal(30,15)),
        shared_projects,
        cast(project_costs AS JSON),
        cast(source_uuid AS UUID)
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}};

-- Clear out old entries first
INSERT
  INTO postgres.{{schema | sqlsafe}}.presto_delete_wrapper_log
       (
           id,
           action_ts,
           table_name,
           where_clause,
           result_rows
       )
VALUES (
    uuid(),
    now(),
    'reporting_ocpawscostlineitem_project_daily_summary',
    'where usage_start >= '{{start_date}}'::date ' ||
      'and usage_start <= '{{end_date}}'::date ' ||
      'and cluster_id = '{{cluster_id}}' ' ||
      'and cost_entry_bill_id = {{bill_id}} ',
    null
)
;

INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    pod_labels,
    resource_id,
    usage_start,
    usage_end,
    product_code,
    product_family,
    instance_type,
    cost_entry_bill_id,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    normalized_usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    pod_cost,
    project_markup_cost,
    source_uuid
)
    SELECT uuid(),
        report_period_id,
        cluster_id,
        cluster_alias,
        data_source,
        namespace,
        node,
        json_parse(pod_labels),
        resource_id,
        usage_start,
        usage_end,
        product_code,
        product_family,
        instance_type,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        availability_zone,
        region,
        unit,
        cast(usage_amount AS decimal(24,9)),
        normalized_usage_amount,
        currency_code,
        cast(unblended_cost AS decimal(30,15)),
        cast(markup_cost AS decimal(30,15)),
        cast(project_cost AS decimal(30,15)),
        cast(project_markup_cost AS decimal(30,15)),
        cast(source_uuid as UUID)
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}};
