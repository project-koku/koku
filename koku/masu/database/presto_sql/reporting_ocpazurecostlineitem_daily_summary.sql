-- The Python Jinja string variable subsitutions azure_where_clause and ocp_where_clause
-- optionally filter azure and OCP data by provider/source
-- Ex azure_where_clause: 'AND cost_entry_bill_id IN (1, 2, 3)'
-- Ex ocp_where_clause: "AND cluster_id = 'abcd-1234`"
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} AS (
    WITH cte_unnested_azure_tags AS (
        SELECT tags.*,
            b.billing_period_start
        FROM (
            SELECT key,
                value,
                cost_entry_bill_id
            FROM postgres.{{schema | sqlsafe}}.reporting_azuretags_summary AS ts
            CROSS JOIN UNNEST("values") AS v(value)
        ) AS tags
        JOIN postgres.{{schema | sqlsafe}}.reporting_azurecostentrybill AS b
            ON tags.cost_entry_bill_id = b.id
        JOIN postgres.{{schema | sqlsafe}}.reporting_azureenabledtagkeys as enabled_tags
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
        SELECT azure.key,
            azure.value,
            azure.cost_entry_bill_id,
            ocp.report_period_id
        FROM cte_unnested_azure_tags AS azure
        JOIN cte_unnested_ocp_pod_tags AS ocp
            ON lower(azure.key) = lower(ocp.key)
                AND lower(azure.value) = lower(ocp.value)
                AND azure.billing_period_start = ocp.report_period_start

        UNION

        SELECT azure.key,
            azure.value,
            azure.cost_entry_bill_id,
            ocp.report_period_id
        FROM cte_unnested_azure_tags AS azure
        JOIN cte_unnested_ocp_volume_tags AS ocp
            ON lower(azure.key) = lower(ocp.key)
                AND lower(azure.value) = lower(ocp.value)
                AND azure.billing_period_start = ocp.report_period_start
    ) AS matches
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}} AS (
    WITH cte_line_items AS (
        SELECT {{bill_id | sqlsafe}} as cost_entry_bill_id,
            cast(uuid() as varchar) as line_item_id,
            date(coalesce(date, usagedatetime)) as usage_date,
            coalesce(subscriptionid, subscriptionguid) as subscription_guid,
            json_extract_scalar(json_parse(azure.additionalinfo), '$.ServiceType') as instance_type,
            coalesce(servicename, metercategory) as service_name,
            resourcelocation as resource_location,
            split_part(coalesce(resourceid, instanceid), '/', 9) as resource_id,
            cast(coalesce(quantity, usagequantity) as decimal(24,9)) as usage_quantity,
            cast(coalesce(costinbillingcurrency, pretaxcost) as decimal(24,9)) as pretax_cost,
            coalesce(billingcurrencycode, currency) as currency,
            CASE
                WHEN split_part(unitofmeasure, ' ', 2) != '' AND NOT (unitofmeasure = '100 Hours' AND metercategory='Virtual Machines')
                    THEN cast(split_part(unitofmeasure, ' ', 1) as integer)
                ELSE 1
                END as multiplier,
            CASE
                WHEN split_part(unitofmeasure, ' ', 2) = 'Hours'
                    THEN  'Hrs'
                WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                    THEN  'GB-Mo'
                WHEN split_part(unitofmeasure, ' ', 2) != ''
                    THEN  split_part(unitofmeasure, ' ', 2)
                ELSE unitofmeasure
            END as unit_of_measure,
            tags,
            lower(tags) as lower_tags
        FROM hive.{{schema | sqlsafe}}.azure_line_items as azure
        WHERE azure.source = '{{azure_source_uuid | sqlsafe}}'
            AND azure.year = '{{year | sqlsafe}}'
            AND azure.month = '{{month | sqlsafe}}'
            AND date(coalesce(date, usagedatetime)) >= date('{{start_date | sqlsafe}}')
            AND date(coalesce(date, usagedatetime)) <= date('{{end_date | sqlsafe}}')
    )
    SELECT azure.cost_entry_bill_id,
        azure.line_item_id,
        azure.usage_date,
        azure.subscription_guid,
        azure.instance_type,
        azure.service_name,
        azure.resource_location,
        azure.resource_id,
        azure.usage_quantity * azure.multiplier as usage_quantity,
        azure.pretax_cost,
        azure.currency,
        azure.unit_of_measure,
        azure.tags,
        azure.lower_tags
    FROM cte_line_items AS azure
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_azure_tags_{{uuid | sqlsafe}} AS (
    SELECT azure.*
    FROM (
        SELECT azure.*,
            row_number() OVER (PARTITION BY azure.line_item_id ORDER BY azure.line_item_id) as row_number
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}} as azure
        JOIN hive.{{schema | sqlsafe}}.__matched_tags_{{uuid | sqlsafe}} as tag
            ON json_extract_scalar(azure.tags, '$.' || tag.key) = tag.value
    ) AS azure
    WHERE azure.row_number = 1
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} AS (
    SELECT azure.*
    FROM hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}} as azure
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


-- First we match OCP pod data to azure data using a direct
-- resource id match. This usually means OCP node -> azure EC2 instance ID.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS (
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.resource_id = ocp.resource_id
                AND azure.usage_date = ocp.usage_start
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
            AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
            AND ocp.data_source = 'Pod'
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_resource_id_matched
        GROUP BY azure_id
    )
    SELECT rm.*,
        (rm.pod_usage_cpu_core_hours / rm.node_capacity_cpu_core_hours) * rm.pretax_cost as project_cost,
        shared.shared_projects
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared AS shared
        ON rm.azure_id = shared.azure_id
)
;

-- Next we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_project') = lower(ocp.namespace)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_node') = lower(ocp.node)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

-- Next we match where the pod label key and value
-- and azure tag key and value match directly
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON azure.usage_date = ocp.usage_start
                AND strpos(azure.lower_tags, ocp.tag) != 0
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_pod_tags_{{uuid | sqlsafe}};

-- First we match OCP storage data to Azure data using a direct
-- resource id match. OCP PVC name -> Azure instance ID.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS (
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.resource_id LIKE '%%' || ocp.persistentvolume
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
            AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
            AND ulid.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
)
;


-- Next we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_project') = lower(ocp.namespace)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.azure_id = azure.line_item_id
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
            AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
            AND ulid.azure_id IS NULL
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_node') = lower(ocp.node)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.azure_id = azure.line_item_id
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND ulid.azure_id IS NULL
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON json_extract_scalar(azure.lower_tags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.azure_id = azure.line_item_id
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE ocp.source_uuid = UUID '{{ocp_source_uuid | sqlsafe}}'
            AND ocp.data_source = 'Storage'
            AND ulid.azure_id IS NULL
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id

;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_daily_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_special_case_tags_{{uuid | sqlsafe}}
;


-- Then we match for OpenShift volume data where the volume label key and value
-- and azure tag key and value match directly
 INSERT INTO hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}}
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
            azure.cost_entry_bill_id,
            azure.line_item_id as azure_id,
            azure.usage_date,
            azure.subscription_guid,
            azure.instance_type,
            azure.service_name,
            azure.resource_location,
            azure.resource_id,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.currency,
            azure.unit_of_measure,
            azure.tags
        FROM hive.{{schema | sqlsafe}}.__reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON azure.usage_date = ocp.usage_start
                AND strpos(azure.lower_tags, ocp.tag) != 0
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.line_item_id
        WHERE rm.azure_id IS NULL
    ),
    cte_number_of_shared AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / shared.shared_projects as project_cost,
        shared.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared AS shared
        ON tm.azure_id = shared.azure_id
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocp_storage_tags_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_azure_tags_{{uuid | sqlsafe}}
;


-- The full summary data for Openshift pod<->azure and
-- Openshift volume<->azure matches are UNIONed together
-- with a GROUP BY using the azure ID to deduplicate
-- the azure data. This should ensure that we never double count
-- azure cost or usage.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_pod_project_cost AS (
        SELECT pc.azure_id,
            map_agg(pc.namespace, pc.project_cost) as project_costs
            FROM (
                SELECT li.azure_id,
                    li.namespace,
                    sum(project_cost) as project_cost
                FROM hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
                GROUP BY li.azure_id, li.namespace
            ) AS pc
        GROUP BY pc.azure_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.azure_id,
            map_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.azure_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.azure_id, li.namespace
        ) AS pc
        GROUP BY pc.azure_id
    )
    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        max(li.resource_id) as resource_id,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(li.service_name) as service_name,
        max(li.instance_type) as instance_type,
        max(li.resource_location) as resource_location,
        max(li.currency) as currency,
        max(li.unit_of_measure) as unit_of_measure,
        li.tags,
        max(li.usage_quantity) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        '{{azure_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN cte_pod_project_cost as pc
        ON li.azure_id = pc.azure_id
    -- Dedup on azure line item so we never double count usage or cost
    GROUP BY li.azure_id, li.tags, pc.project_costs

    UNION

    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        max(li.resource_id) as resource_id,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(li.service_name) as service_name,
        max(li.instance_type) as instance_type,
        max(li.resource_location) as resource_location,
        max(li.currency) as currency,
        max(li.unit_of_measure) as unit_of_measure,
        li.tags,
        max(li.usage_quantity) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        '{{azure_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
    JOIN cte_storage_project_cost AS pc
        ON li.azure_id = pc.azure_id
    LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.azure_id = li.azure_id
        AND ulid.azure_id IS NULL
    GROUP BY li.azure_id, li.tags, pc.project_costs
)
;

-- The full summary data for Openshift pod<->azure and
-- Openshift volume<->azure matches are UNIONed together
-- with a GROUP BY using the OCP ID to deduplicate
-- based on OpenShift data. This is effectively the same table
-- as reporting_ocpazurecostlineitem_daily_summary but from the OpenShift
-- point of view. Here usage and cost are divided by the
-- number of pods sharing the cost so the values turn out the
-- same when reported.
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        'Pod' as data_source,
        li.namespace,
        li.node,
        li.pod_labels,
        max(li.resource_id) as resource_id,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(li.service_name) as service_name,
        max(li.instance_type) as instance_type,
        max(li.resource_location) as resource_location,
        max(li.currency) as currency,
        max(li.unit_of_measure) as unit_of_measure,
        li.tags,
        sum(li.usage_quantity / li.shared_projects) as usage_quantity,
        sum(li.pretax_cost / li.shared_projects) as pretax_cost,
        sum(li.pretax_cost / li.shared_projects) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        li.project_cost,
        li.project_cost * cast({{markup}} as decimal(24,9)) as project_markup_cost,
        '{{azure_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
    -- Grouping by OCP this time for the by project view
    GROUP BY li.report_period_id,
        li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.pod_labels,
        li.project_cost,
        li.tags

    UNION

    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        'Storage' as data_source,
        li.namespace,
        li.node,
        li.volume_labels as pod_labels,
        max(li.resource_id) as resource_id,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(li.service_name) as service_name,
        max(li.instance_type) as instance_type,
        max(li.resource_location) as resource_location,
        max(li.currency) as currency,
        max(li.unit_of_measure) as unit_of_measure,
        li.tags,
        sum(li.usage_quantity / li.shared_projects) as usage_quantity,
        sum(li.pretax_cost / li.shared_projects) as pretax_cost,
        sum(li.pretax_cost / li.shared_projects) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(li.shared_projects) as shared_projects,
        li.project_cost,
        li.project_cost * cast({{markup}} as decimal(24,9)) as project_markup_cost,
        '{{azure_source_uuid | sqlsafe}}' as source_uuid
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
    LEFT JOIN hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.azure_id = li.azure_id
    WHERE ulid.azure_id IS NULL
    GROUP BY li.ocp_id,
        li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.volume_labels,
        li.project_cost,
        li.tags
)
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}};

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}};


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
    'reporting_ocpazurecostlineitem_daily_summary',
    'WHERE usage_start >= '{{start_date}}'::date ' ||
      'AND usage_start <= '{{end_date}}'::date ' ||
      'AND cluster_id = '{{cluster_id}}' ' ||
      'AND cost_entry_bill_id = {{bill_id}} ',
    null
)
;

-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    resource_id,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    subscription_guid,
    instance_type,
    service_name,
    resource_location,
    tags,
    usage_quantity,
    pretax_cost,
    markup_cost,
    currency,
    unit_of_measure,
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
        cost_entry_bill_id,
        subscription_guid,
        instance_type,
        service_name,
        resource_location,
        json_parse(tags),
        cast(usage_quantity AS decimal(24,9)),
        cast(pretax_cost AS decimal(30,15)),
        cast(markup_cost  AS decimal(30,15)),
        currency,
        unit_of_measure,
        shared_projects,
        cast(project_costs AS JSON),
        cast(source_uuid AS UUID)
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}};

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
    'reporting_ocpazurecostlineitem_project_daily_summary',
    'where usage_start >= '{{start_date}}'::date ' ||
      'and usage_start <= '{{end_date}}'::date ' ||
      'and cluster_id = '{{cluster_id}}' ' ||
      'and cost_entry_bill_id = {{bill_id}} ',
    null
)
;

INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary (
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
    cost_entry_bill_id,
    subscription_guid,
    instance_type,
    service_name,
    resource_location,
    usage_quantity,
    pretax_cost,
    markup_cost,
    currency,
    unit_of_measure,
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
        cost_entry_bill_id,
        subscription_guid,
        instance_type,
        service_name,
        resource_location,
        cast(usage_quantity AS decimal(24,9)),
        cast(pretax_cost AS decimal(30,15)),
        cast(markup_cost AS decimal(30,15)),
        currency,
        unit_of_measure,
        cast(project_cost AS decimal(30,15)),
        cast(project_markup_cost AS decimal(30,15)),
        cast(source_uuid as UUID)
    FROM hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}}
;

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}};
