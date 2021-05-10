DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND cluster_id = {{cluster_id}}
    AND infrastructure_raw_cost IS NOT NULL
;

CREATE TEMPORARY TABLE matched_tags_{{uuid | sqlsafe}} AS (
    WITH cte_unnested_azure_tags AS (
        SELECT tags.*,
            b.billing_period_start
        FROM (
            SELECT key,
                value,
                cost_entry_bill_id,
                subscription_guid
            FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts,
                unnest(ts.values) AS values(value)
        ) AS tags
        JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill AS b
            ON tags.cost_entry_bill_id = b.id
        JOIN {{schema | sqlsafe}}.reporting_azureenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        {% if bill_ids %}
        WHERE b.id IN (
            {%- for bill_id in bill_ids -%}
            {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%}
        )
        {% endif %}

    ),
    cte_unnested_ocp_pod_tags AS (
        SELECT tags.*,
            rp.report_period_start,
            rp.cluster_id,
            rp.cluster_alias
        FROM (
            SELECT key,
                value,
                report_period_id,
                namespace
            FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ts,
                unnest(ts.values) AS values(value)
        ) AS tags
        JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
            ON tags.report_period_id = rp.id
        -- Filter out tags that aren't enabled
        JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        {% if cluster_id %}
        WHERE rp.cluster_id = {{cluster_id}}
        {% endif %}
    ),
    cte_unnested_ocp_volume_tags AS (
        SELECT tags.*,
            rp.report_period_start,
            rp.cluster_id,
            rp.cluster_alias
        FROM (
            SELECT key,
                value,
                report_period_id,
                namespace
            FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ts,
                unnest(ts.values) AS values(value)
        ) AS tags
        JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
            ON tags.report_period_id = rp.id
        -- Filter out tags that aren't enabled
        JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
            ON lower(enabled_tags.key) = lower(tags.key)
        {% if cluster_id %}
        WHERE rp.cluster_id = {{cluster_id}}
        {% endif %}
    )
    SELECT jsonb_build_object(key, value) as tag,
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


-- Selects the data from azure daily and includes only
-- the enabled tags in the results
CREATE TEMPORARY TABLE reporting_azure_with_enabled_tags_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM {{schema | sqlsafe}}.reporting_azureenabledtagkeys
    ),
    cte_filtered_azure_tags AS (
        SELECT id,
            jsonb_object_agg(key,value) as azure_tags
        FROM (
            SELECT lid.id,
                lid.tags as azure_tags,
                aak.key_array
            FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.tags ?| aak.key_array
                AND lid.usage_date >= {{start_date}}::date
                AND lid.usage_date <= {{end_date}}::date
                --azure_where_clause
                {% if bill_ids %}
                AND lid.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%}
                )
                {% endif %}
        ) AS lid,
        jsonb_each_text(lid.azure_tags) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    )
    SELECT azure.id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            fvl.azure_tags as tags
    FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as azure
    LEFT JOIN cte_filtered_azure_tags as fvl
        ON azure.id = fvl.id
)
;

CREATE TEMPORARY TABLE reporting_azure_tags_{{uuid | sqlsafe}} AS (
    SELECT azure.*
    FROM (
        SELECT azure.*,
            lower(azure.tags::text)::jsonb as lower_tags,
            row_number() OVER (PARTITION BY azure.id ORDER BY azure.id) as row_number,
            tag.key,
            tag.value
            FROM reporting_azure_with_enabled_tags_{{uuid | sqlsafe}} as azure
            JOIN matched_tags_{{uuid | sqlsafe}} as tag
                ON azure.cost_entry_bill_id = tag.cost_entry_bill_id
                    AND azure.tags @> tag.tag
            WHERE azure.usage_date >= {{start_date}}::date
                AND azure.usage_date <= {{end_date}}::date
                --azure_where_clause
                {% if bill_ids %}
                AND azure.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%}
                )
                {% endif %}
    ) AS azure
    WHERE azure.row_number = 1
)
;

DROP INDEX IF EXISTS azure_tags_gin_idx
;
CREATE INDEX azure_tags_gin_idx ON reporting_azure_tags_{{uuid | sqlsafe}} USING GIN (lower_tags)
;


CREATE TEMPORARY TABLE reporting_azure_special_case_tags_{{uuid | sqlsafe}} AS (
    WITH cte_tag_options AS (
        SELECT jsonb_build_object(key, value) as tag,
            key,
            value,
            cost_entry_bill_id
        FROM (
            SELECT key,
                value,
                ts.cost_entry_bill_id
            FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts,
                unnest(values) AS values(value)
            --azure_where_clause
            {% if bill_ids %}
            WHERE ts.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
        ) AS keyval
        WHERE lower(key) IN ('openshift_cluster', 'openshift_node', 'openshift_project', 'kubernetes.io-created-for-pv-name')
    )
    SELECT azure.*,
        lower(tag.key) as key,
        lower(tag.value) as value
    FROM reporting_azure_with_enabled_tags_{{uuid | sqlsafe}} as azure
    JOIN cte_tag_options as tag
            ON azure.cost_entry_bill_id = tag.cost_entry_bill_id
                AND azure.tags @> tag.tag
    WHERE azure.usage_date >= {{start_date}}::date
        AND azure.usage_date <= {{end_date}}::date
        --azure_where_clause
        {% if bill_ids %}
        AND azure.cost_entry_bill_id IN (
            {%- for bill_id in bill_ids -%}
            {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%}
        )
        {% endif %}
)
;

CREATE TEMPORARY TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}} AS (
    SELECT ocp.*,
        lower(tag.tag::text)::jsonb as tag
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN matched_tags_{{uuid | sqlsafe}} AS tag
        ON ocp.report_period_id = tag.report_period_id
            AND ocp.volume_labels @> tag.tag
    WHERE ocp.usage_start >= {{start_date}}::date
        AND ocp.usage_start <= {{end_date}}::date
        AND ocp.data_source = 'Storage'
        --ocp_where_clause
        {% if cluster_id %}
        AND cluster_id = {{cluster_id}}
        {% endif %}
)
;

CREATE TEMPORARY TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}} AS (
    SELECT ocp.*,
        lower(tag.tag::text)::jsonb as tag
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN matched_tags_{{uuid | sqlsafe}} AS tag
        ON ocp.report_period_id = tag.report_period_id
            AND ocp.pod_labels @> tag.tag
    WHERE ocp.usage_start >= {{start_date}}::date
        AND ocp.usage_start <= {{end_date}}::date
        AND ocp.data_source = 'Pod'
        --ocp_where_clause
        {% if cluster_id %}
        AND cluster_id = {{cluster_id}}
        {% endif %}
)
;

-- no need to wait for commit
TRUNCATE TABLE matched_tags_{{uuid | sqlsafe}};
DROP TABLE matched_tags_{{uuid | sqlsafe}};


-- First we match OCP pod data to Azure data using a direct
-- resource id match. This usually means OCP node -> Azure Virutal Machine.
CREATE TEMPORARY TABLE reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS (
    WITH cte_resource_id_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_with_enabled_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice as aps
            ON azure.cost_entry_product_id = aps.id
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            -- NOTE: We would normally use ocp.resource_id
            -- For this JOIN, but it is not guaranteed to be correct
            -- in the current Operator Metering version
            -- so we are matching only on the node name
            -- which should match the split Azure instance ID
            ON split_part(aps.instance_id, '/', 9) = ocp.node
                AND azure.usage_date = ocp.usage_start
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Pod'
            -- azure_where_clause
            {% if bill_ids %}
            AND cost_entry_bill_id IN (
                {%- for bill_id in bill_ids -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
            --ocp_where_clause
            {% if cluster_id %}
            AND cluster_id = {{cluster_id}}
            {% endif %}
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_resource_id_matched
        GROUP BY azure_id
    )
    SELECT rm.*,
        (rm.pod_usage_cpu_core_hours / rm.node_capacity_cpu_core_hours) * rm.pretax_cost as project_cost,
        sp.shared_projects
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared_projects AS sp
        ON rm.azure_id = sp.azure_id
)
;

-- Next we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
INSERT INTO reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.key = 'openshift_project' AND azure.value = lower(ocp.namespace)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.key = 'openshift_node' AND azure.value = lower(ocp.node)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
INSERT INTO reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON (azure.key = 'openshift_cluster' AND azure.value = lower(ocp.cluster_id)
                OR azure.key = 'openshift_cluster' AND azure.value = lower(ocp.cluster_alias))
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Pod'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- Next we match where the pod label key and value
-- and Azure tag key and value match directly
INSERT INTO reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON azure.lower_tags @> ocp.tag
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}};


-- First we match OCP storage data to Azure data using a direct
-- resource id match. OCP PVC name -> Azure instance ID.
CREATE TEMPORARY TABLE reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS (
    WITH cte_resource_id_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_with_enabled_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice as aps
            ON azure.cost_entry_product_id = aps.id
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            -- Need the doubl percent here for Jinja templating
            ON split_part(aps.instance_id, '/', 9) LIKE '%%' || ocp.persistentvolume
                AND azure.usage_date = ocp.usage_start
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            -- azure_where_clause
            {% if bill_ids %}
            AND cost_entry_bill_id IN (
                {%- for bill_id in bill_ids -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
            --ocp_where_clause
            {% if cluster_id %}
            AND cluster_id = {{cluster_id}}
            {% endif %}
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_resource_id_matched
        GROUP BY azure_id
    )
    SELECT rm.*,
        (rm.persistentvolumeclaim_usage_gigabyte_months / rm.persistentvolumeclaim_capacity_gigabyte_months) * rm.pretax_cost as project_cost,
        sp.shared_projects
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared_projects AS sp
        ON rm.azure_id = sp.azure_id
)
;

-- Then we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
INSERT INTO reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.key = 'openshift_project' AND azure.value = lower(ocp.namespace)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
 INSERT INTO reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.key = 'openshift_node' AND azure.value = lower(ocp.node)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
 )
 ;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
INSERT INTO reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON (azure.key = 'openshift_cluster' AND azure.value = lower(ocp.cluster_id)
                OR azure.key = 'openshift_cluster' AND azure.value = lower(ocp.cluster_alias))
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- Next we match where the azure tag is kubernetes.io-created-for-pv-name
 INSERT INTO reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_special_case_tags_{{uuid | sqlsafe}} as azure
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON azure.key = 'kubernetes.io-created-for-pv-name'
                AND azure.value = lower(ocp.persistentvolume)
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
 )
 ;

-- no need to wait for commit
TRUNCATE TABLE reporting_azure_special_case_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_azure_special_case_tags_{{uuid | sqlsafe}};


-- Then we match for OpenShift volume data where the volume label key and value
-- and azure tag key and value match directly
INSERT INTO reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} (
    WITH cte_tag_matched AS (
        SELECT ocp.uuid AS ocp_id,
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
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON azure.lower_tags @> ocp.tag
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / sp.shared_projects as project_cost,
        sp.shared_projects
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_azure_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_azure_tags_{{uuid | sqlsafe}};

TRUNCATE TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}};


-- The full summary data for Openshift pod<->azure and
-- Openshift volume<->azure matches are UNIONed together
-- with a GROUP BY using the azure ID to deduplicate
-- the azure data. This should ensure that we never double count
-- azure cost or usage.
CREATE TEMPORARY TABLE reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_split_units_usage AS (
        SELECT li.azure_id,
            CASE WHEN split_part(m.unit_of_measure, ' ', 2) != '' AND NOT (m.unit_of_measure = '100 Hours' AND m.meter_category='Virtual Machines')
                THEN  split_part(m.unit_of_measure, ' ', 1)::integer
                ELSE 1::integer
                END as multiplier,
            CASE
                WHEN split_part(m.unit_of_measure, ' ', 2) = 'Hours'
                    THEN  'Hrs'
                WHEN split_part(m.unit_of_measure, ' ', 2) = 'GB/Month'
                    THEN  'GB-Mo'
                WHEN split_part(m.unit_of_measure, ' ', 2) != ''
                    THEN  split_part(m.unit_of_measure, ' ', 2)
                ELSE m.unit_of_measure
            END as unit_of_measure
        FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS li
        JOIN {{schema | safe}}.reporting_azuremeter AS m
            ON li.meter_id = m.id
    ),
    cte_split_units_storage AS (
        SELECT li.azure_id,
            CASE WHEN split_part(m.unit_of_measure, ' ', 2) != '' AND NOT (m.unit_of_measure = '100 Hours' AND m.meter_category='Virtual Machines')
                THEN  split_part(m.unit_of_measure, ' ', 1)::integer
                ELSE 1::integer
                END as multiplier,
            CASE
                WHEN split_part(m.unit_of_measure, ' ', 2) = 'Hours'
                    THEN  'Hrs'
                WHEN split_part(m.unit_of_measure, ' ', 2) = 'GB/Month'
                    THEN  'GB-Mo'
                WHEN split_part(m.unit_of_measure, ' ', 2) != ''
                    THEN  split_part(m.unit_of_measure, ' ', 2)
                ELSE m.unit_of_measure
            END as unit_of_measure
        FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
        JOIN {{schema | safe}}.reporting_azuremeter AS m
            ON li.meter_id = m.id
    ),
    cte_pod_project_cost AS (
        SELECT pc.azure_id,
            jsonb_object_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.azure_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.azure_id, li.namespace
        ) AS pc
        GROUP BY pc.azure_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.azure_id,
            jsonb_object_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.azure_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.azure_id, li.namespace
        ) AS pc
        GROUP BY pc.azure_id
    )
    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        NULL as persistentvolumeclaim,
        NULL as persistentvolume,
        NULL as storageclass,
        'Pod' as data_source,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(suu.unit_of_measure) as unit_of_measure,
        li.tags,
        jsonb_agg(distinct li.pod_labels) as pod_labels,
        count(distinct li.pod_labels) as pod_label_count,
        max(li.usage_quantity * suu.multiplier) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    JOIN cte_pod_project_cost as pc
        ON li.azure_id = pc.azure_id
    JOIN cte_split_units_usage as suu
        ON li.azure_id = suu.azure_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_date >= {{start_date}}::date
        AND li.usage_date <= {{end_date}}::date
    -- Dedup on azure line item so we never double count usage or cost
    GROUP BY li.azure_id, li.tags, pc.project_costs, ab.provider_id

    UNION

    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        max(li.node) as node,
        max(li.persistentvolumeclaim) as persistentvolumeclaim,
        max(li.persistentvolume) as persistentvolume,
        max(li.storageclass) as storageclass,
        'Storage' as data_source,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(sus.unit_of_measure) as unit_of_measure,
        li.tags,
        jsonb_agg(distinct li.volume_labels) as pod_labels,
        count(distinct li.volume_labels) as pod_label_count,
        max(li.usage_quantity * sus.multiplier) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    JOIN cte_storage_project_cost AS pc
        ON li.azure_id = pc.azure_id
    JOIN cte_split_units_storage as sus
        ON li.azure_id = sus.azure_id
    LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.azure_id = li.azure_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_date >= {{start_date}}::date
        AND li.usage_date <= {{end_date}}::date
        AND ulid.azure_id IS NULL
    GROUP BY li.azure_id, li.tags, pc.project_costs, ab.provider_id
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
CREATE TEMPORARY TABLE reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.data_source,
        project as "namespace",
        pod_label as pod_labels,
        li.node,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.usage_start,
        li.usage_end,
        li.cost_entry_bill_id,
        li.subscription_guid,
        li.service_name,
        li.instance_type,
        li.resource_location,
        li.resource_id,
        li.currency,
        li.unit_of_measure,
        li.usage_quantity / li.pod_label_count / li.shared_projects as usage_quantity,
        li.pretax_cost / li.pod_label_count / li.shared_projects as pretax_cost,
        li.pretax_cost / li.pod_label_count / li.shared_projects * {{markup}}::numeric as markup_cost,
        project_cost::numeric as project_cost,
        project_cost::numeric * {{markup}}::numeric as project_markup_cost,
        li.source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}} as li,
        jsonb_array_elements(li.pod_labels) AS pod_labels(pod_label),
        jsonb_each_text(li.project_costs) AS project_costs(project, project_cost)
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}};

TRUNCATE TABLE reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}};


-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    --azure_where_clause
    {% if bill_ids %}
    AND cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    --ocp_where_clause
    {% if cluster_id %}
    AND cluster_id = {{cluster_id}}
    {% endif %}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary (
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
    SELECT uuid_generate_v4(),
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
    FROM reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}}
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}};


DELETE FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    --azure_where_clause
    {% if bill_ids %}
    AND cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    --ocp_where_clause
    {% if cluster_id %}
    AND cluster_id = {{cluster_id}}
    {% endif %}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
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
    SELECT uuid_generate_v4(),
        report_period_id,
        cluster_id,
        cluster_alias,
        data_source,
        namespace,
        node,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
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
        project_cost,
        project_markup_cost,
        source_uuid
    FROM reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}}
;

DROP INDEX IF EXISTS azure_tags_gin_idx;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}};

-- Update infra raw costs in OCP table
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    namespace,
    data_source,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    pod_labels,
    volume_labels,
    source_uuid,
    infrastructure_raw_cost,
    infrastructure_project_raw_cost,
    infrastructure_usage_cost,
    supplementary_usage_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months
)
    SELECT uuid_generate_v4() as uuid,
        ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.persistentvolumeclaim,
        max(ocp_azure.persistentvolume),
        max(ocp_azure.storageclass),
        ocp_azure.resource_id,
        CASE WHEN ocp_azure.data_source = 'Pod'
            THEN ocp_azure.pod_labels
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_azure.data_source = 'Storage'
            THEN ocp_azure.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        rp.provider_id as source_uuid,
        sum(ocp_azure.pretax_cost + ocp_azure.markup_cost) AS infrastructure_raw_cost,
        sum(ocp_azure.pod_cost + ocp_azure.project_markup_cost) AS infrastructure_project_raw_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as infrastructure_usage_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as supplementary_usage_cost,
        0 as pod_usage_cpu_core_hours,
        0 as pod_request_cpu_core_hours,
        0 as pod_limit_cpu_core_hours,
        0 as pod_usage_memory_gigabyte_hours,
        0 as pod_request_memory_gigabyte_hours,
        0 as pod_limit_memory_gigabyte_hours,
        0 as node_capacity_cpu_cores,
        0 as node_capacity_cpu_core_hours,
        0 as node_capacity_memory_gigabytes,
        0 as node_capacity_memory_gigabyte_hours,
        0 as cluster_capacity_cpu_core_hours,
        0 as cluster_capacity_memory_gigabyte_hours,
        0 as persistentvolumeclaim_capacity_gigabyte,
        0 as persistentvolumeclaim_capacity_gigabyte_months,
        0 as volume_request_storage_gigabyte_months,
        0 as persistentvolumeclaim_usage_gigabyte_months
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary AS ocp_azure
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_azure.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_azure.usage_start)::date  = date(rp.report_period_start)
    WHERE ocp_azure.usage_start >= {{start_date}}::date
        AND ocp_azure.usage_start <= {{end_date}}::date
        AND ocp_azure.cluster_id = {{cluster_id}}
    GROUP BY ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.persistentvolumeclaim,
        ocp_azure.resource_id,
        ocp_azure.pod_labels,
        rp.provider_id
;
