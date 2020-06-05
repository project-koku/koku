-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_azure_tags_{{uuid | sqlsafe}} AS (
    SELECT azure.*,
        LOWER(key) as key,
        LOWER(value) as value
        FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as azure,
            jsonb_each_text(azure.tags) labels
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            --azure_where_clause
            {% if bill_ids %}
            AND cost_entry_bill_id IN (
                {%- for bill_id in bill_ids -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
)
;

-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}} AS (
    SELECT ocp.*
    FROM (
        SELECT ocp.*,
            LOWER(key) as key,
            LOWER(value) as value
        FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily as ocp,
            jsonb_each_text(ocp.persistentvolume_labels) labels
        WHERE ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            --ocp_where_clause
            {% if cluster_id %}
            AND cluster_id = {{cluster_id}}
            {% endif %}

        UNION ALL

        SELECT ocp.*,
            LOWER(key) as key,
            LOWER(value) as value
        FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily as ocp,
            jsonb_each_text(ocp.persistentvolumeclaim_labels) labels
        WHERE ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            --ocp_where_clause
            {% if cluster_id %}
            AND cluster_id = {{cluster_id}}
            {% endif %}
    ) AS ocp
    INNER JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON LOWER(enabled_tags.key) = ocp.key
)
;

-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}} AS (
    SELECT ocp.*
    FROM (
        SELECT ocp.*,
            LOWER(key) as key,
            LOWER(value) as value
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp,
            jsonb_each_text(ocp.pod_labels) labels
        WHERE ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            --ocp_where_clause
            {% if cluster_id %}
            AND cluster_id = {{cluster_id}}
            {% endif %}
    ) AS ocp
    INNER JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON LOWER(enabled_tags.key) = ocp.key
)
;

-- First we match OCP pod data to Azure data using a direct
-- resource id match. This usually means OCP node -> Azure Virutal Machine.
CREATE TEMPORARY TABLE reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}} AS (
    WITH cte_resource_id_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_seconds,
            ocp.pod_request_cpu_core_seconds,
            ocp.pod_limit_cpu_core_seconds,
            ocp.pod_usage_memory_byte_seconds,
            ocp.pod_request_memory_byte_seconds,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_seconds,
            ocp.node_capacity_memory_bytes,
            ocp.node_capacity_memory_byte_seconds,
            ocp.cluster_capacity_cpu_core_seconds,
            ocp.cluster_capacity_memory_byte_seconds,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as azure
        JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice as aps
            ON azure.cost_entry_product_id = aps.id
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp
            -- NOTE: We would normally use ocp.resource_id
            -- For this JOIN, but it is not guaranteed to be correct
            -- in the current Operator Metering version
            -- so we are matching only on the node name
            -- which should match the split Azure instance ID
            ON split_part(aps.instance_id, '/', 9) = ocp.node
                AND azure.usage_date = ocp.usage_start
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
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
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_resource_id_matched
        GROUP BY azure_id
    )
    SELECT rm.*,
        (rm.pod_usage_cpu_core_seconds / rm.node_capacity_cpu_core_seconds) * rm.pretax_cost as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared_projects AS sp
        ON rm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON rm.azure_id = spod.azure_id

)
;

-- Next we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
CREATE TEMPORARY TABLE reporting_ocp_azure_openshift_project_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_seconds,
            ocp.pod_request_cpu_core_seconds,
            ocp.pod_limit_cpu_core_seconds,
            ocp.pod_usage_memory_byte_seconds,
            ocp.pod_request_memory_byte_seconds,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_seconds,
            ocp.node_capacity_memory_bytes,
            ocp.node_capacity_memory_byte_seconds,
            ocp.cluster_capacity_cpu_core_seconds,
            ocp.cluster_capacity_memory_byte_seconds,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON azure.key = 'openshift_project' AND azure.value = lower(ocp.namespace)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}} AS rm
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
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
CREATE TEMPORARY TABLE reporting_ocp_azure_openshift_node_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_seconds,
            ocp.pod_request_cpu_core_seconds,
            ocp.pod_limit_cpu_core_seconds,
            ocp.pod_usage_memory_byte_seconds,
            ocp.pod_request_memory_byte_seconds,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_seconds,
            ocp.node_capacity_memory_bytes,
            ocp.node_capacity_memory_byte_seconds,
            ocp.cluster_capacity_cpu_core_seconds,
            ocp.cluster_capacity_memory_byte_seconds,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON azure.key = 'openshift_node' AND azure.value = lower(ocp.node)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
CREATE TEMPORARY TABLE reporting_ocp_azure_openshift_cluster_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_seconds,
            ocp.pod_request_cpu_core_seconds,
            ocp.pod_limit_cpu_core_seconds,
            ocp.pod_usage_memory_byte_seconds,
            ocp.pod_request_memory_byte_seconds,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_seconds,
            ocp.node_capacity_memory_bytes,
            ocp.node_capacity_memory_byte_seconds,
            ocp.cluster_capacity_cpu_core_seconds,
            ocp.cluster_capacity_memory_byte_seconds,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON (azure.key = 'openshift_cluster' AND azure.value = ocp.cluster_id
                OR azure.key = 'openshift_cluster' AND azure.value = ocp.cluster_alias)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_node_tag_matched_{{uuid | sqlsafe}} as ntm
            ON ntm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
            AND ntm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Next we match where the pod label key and value
-- and Azure tag key and value match directly
CREATE TEMPORARY TABLE reporting_ocp_azure_direct_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.pod_labels,
            ocp.pod_usage_cpu_core_seconds,
            ocp.pod_request_cpu_core_seconds,
            ocp.pod_limit_cpu_core_seconds,
            ocp.pod_usage_memory_byte_seconds,
            ocp.pod_request_memory_byte_seconds,
            ocp.node_capacity_cpu_cores,
            ocp.node_capacity_cpu_core_seconds,
            ocp.node_capacity_memory_bytes,
            ocp.node_capacity_memory_byte_seconds,
            ocp.cluster_capacity_cpu_core_seconds,
            ocp.cluster_capacity_memory_byte_seconds,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON azure.key = ocp.key
                AND azure.value = ocp.value
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_node_tag_matched_{{uuid | sqlsafe}} as ntm
            ON ntm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_openshift_cluster_tag_matched_{{uuid | sqlsafe}} AS ctm
            ON ctm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
            AND ntm.azure_id IS NULL
            AND ctm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- We UNION the various matches into a table holding all of the
-- OpenShift pod data matches for easier use.
CREATE TEMPORARY TABLE reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS (
    SELECT *
    FROM reporting_ocp_azure_resource_id_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_openshift_project_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_openshift_node_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_openshift_cluster_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_direct_tag_matched_{{uuid | sqlsafe}}
);

-- First we match OCP storage data to Azure data using a direct
-- resource id match. OCP PVC name -> Azure instance ID.
CREATE TEMPORARY TABLE reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}} AS (
    WITH cte_resource_id_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_bytes,
            ocp.persistentvolumeclaim_capacity_byte_seconds,
            ocp.volume_request_storage_byte_seconds,
            ocp.persistentvolumeclaim_usage_byte_seconds,
            ocp.persistentvolume_labels,
            ocp.persistentvolumeclaim_labels,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as azure
        JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice as aps
            ON azure.cost_entry_product_id = aps.id
        JOIN {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily as ocp
            -- Need the doubl percent here for Jinja templating
            ON split_part(aps.instance_id, '/', 9) LIKE '%%' || ocp.persistentvolume
                AND azure.usage_date = ocp.usage_start
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
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
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_resource_id_matched
        GROUP BY azure_id
    )
    SELECT rm.*,
        (rm.persistentvolumeclaim_usage_byte_seconds / rm.persistentvolumeclaim_capacity_byte_seconds) * rm.pretax_cost as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared_projects AS sp
        ON rm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON rm.azure_id = spod.azure_id

)
;

-- Then we match where the azure tag is the special openshift_project key
-- and the value matches an OpenShift project name
CREATE TEMPORARY TABLE reporting_ocp_azure_storage_openshift_project_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_bytes,
            ocp.persistentvolumeclaim_capacity_byte_seconds,
            ocp.volume_request_storage_byte_seconds,
            ocp.persistentvolumeclaim_usage_byte_seconds,
            ocp.persistentvolume_labels,
            ocp.persistentvolumeclaim_labels,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON azure.key = 'openshift_project' AND azure.value = ocp.namespace
                AND azure.usage_date = ocp.usage_start
        LEFT JOIN reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}} AS rm
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
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Next we match where the azure tag is the special openshift_node key
-- and the value matches an OpenShift node name
CREATE TEMPORARY TABLE reporting_ocp_azure_storage_openshift_node_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_bytes,
            ocp.persistentvolumeclaim_capacity_byte_seconds,
            ocp.volume_request_storage_byte_seconds,
            ocp.persistentvolumeclaim_usage_byte_seconds,
            ocp.persistentvolume_labels,
            ocp.persistentvolumeclaim_labels,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON azure.key = 'openshift_node' AND azure.value = ocp.node
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Next we match where the azure tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
CREATE TEMPORARY TABLE reporting_ocp_azure_storage_openshift_cluster_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_bytes,
            ocp.persistentvolumeclaim_capacity_byte_seconds,
            ocp.volume_request_storage_byte_seconds,
            ocp.persistentvolumeclaim_usage_byte_seconds,
            ocp.persistentvolume_labels,
            ocp.persistentvolumeclaim_labels,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON (azure.key = 'openshift_cluster' AND azure.value = ocp.cluster_id
                OR azure.key = 'openshift_cluster' AND azure.value = ocp.cluster_alias)
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_node_tag_matched_{{uuid | sqlsafe}} as ntm
            ON ntm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
            AND ntm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- Then we match for OpenShift volume data where the volume label key and value
-- and azure tag key and value match directly
CREATE TEMPORARY TABLE reporting_ocp_azure_storage_direct_tag_matched_{{uuid | sqlsafe}} AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
            ocp.report_period_id,
            ocp.cluster_id,
            ocp.cluster_alias,
            ocp.namespace,
            ocp.pod,
            ocp.node,
            ocp.persistentvolumeclaim,
            ocp.persistentvolume,
            ocp.storageclass,
            ocp.persistentvolumeclaim_capacity_bytes,
            ocp.persistentvolumeclaim_capacity_byte_seconds,
            ocp.volume_request_storage_byte_seconds,
            ocp.persistentvolumeclaim_usage_byte_seconds,
            ocp.persistentvolume_labels,
            ocp.persistentvolumeclaim_labels,
            azure.id AS azure_id,
            azure.cost_entry_bill_id,
            azure.cost_entry_product_id,
            azure.meter_id,
            azure.subscription_guid,
            azure.usage_date,
            azure.usage_quantity,
            azure.pretax_cost,
            azure.offer_id,
            azure.tags
        FROM reporting_azure_tags_{{uuid | sqlsafe}} as azure
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON (
                    (
                        azure.key = ocp.key
                        AND azure.value = ocp.value
                    )
                OR
                    (
                        azure.key = 'kubernetes.io-created-for-pv-name'
                        AND azure.value = ocp.persistentvolume
                    )
            )
                AND azure.usage_date = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}} AS rm
            ON rm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_project_tag_matched_{{uuid | sqlsafe}} as ptm
            ON ptm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_node_tag_matched_{{uuid | sqlsafe}} as ntm
            ON ntm.azure_id = azure.id
        LEFT JOIN reporting_ocp_azure_storage_openshift_cluster_tag_matched_{{uuid | sqlsafe}} AS ctm
            ON ctm.azure_id = azure.id
        WHERE azure.usage_date >= {{start_date}}::date
            AND azure.usage_date <= {{end_date}}::date
            AND rm.azure_id IS NULL
            AND ptm.azure_id IS NULL
            AND ntm.azure_id IS NULL
            AND ctm.azure_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT azure_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY azure_id
    ),
    cte_number_of_shared_pods AS (
        SELECT azure_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY azure_id
    )
    SELECT tm.*,
        tm.pretax_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.azure_id = sp.azure_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.azure_id = spod.azure_id
)
;

-- We UNION the various matches into a table holding all of the
-- OpenShift volume data matches for easier use.
CREATE TEMPORARY TABLE reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS (
    SELECT *
    FROM reporting_ocp_azure_storage_resource_id_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_storage_openshift_project_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_storage_openshift_node_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_storage_openshift_cluster_tag_matched_{{uuid | sqlsafe}}

    UNION

    SELECT *
    FROM reporting_ocp_azure_storage_direct_tag_matched_{{uuid | sqlsafe}}
);

-- The full summary data for Openshift pod<->azure and
-- Openshift volume<->azure matches are UNIONed together
-- with a GROUP BY using the azure ID to deduplicate
-- the azure data. This should ensure that we never double count
-- azure cost or usage.
CREATE TEMPORARY TABLE reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_pod_project_cost AS (
        SELECT pc.azure_id,
            jsonb_object_agg(pc.namespace, pc.pod_cost) as project_costs
        FROM (
            SELECT li.azure_id,
                li.namespace,
                sum(pod_cost) as pod_cost
            FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.azure_id, li.namespace
        ) AS pc
        GROUP BY pc.azure_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.azure_id,
            jsonb_object_agg(pc.namespace, pc.pod_cost) as project_costs
        FROM (
            SELECT li.azure_id,
                li.namespace,
                sum(pod_cost) as pod_cost
            FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.azure_id, li.namespace
        ) AS pc
        GROUP BY pc.azure_id
    )
    SELECT max(li.report_period_id) as report_period_id,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        array_agg(DISTINCT li.pod) as pod,
        max(li.node) as node,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(m.unit_of_measure) as unit_of_measure,
        li.tags,
        max(li.usage_quantity) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        max(li.offer_id) as offer_id,
        pc.project_costs as project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    JOIN cte_pod_project_cost as pc
        ON li.azure_id = pc.azure_id
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
        array_agg(DISTINCT li.pod) as pod,
        max(li.node) as node,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(m.unit_of_measure) as unit_of_measure,
        li.tags,
        max(li.usage_quantity) as usage_quantity,
        max(li.pretax_cost) as pretax_cost,
        max(li.pretax_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        max(li.offer_id) as offer_id,
        pc.project_costs as project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    JOIN cte_storage_project_cost AS pc
        ON li.azure_id = pc.azure_id
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
        'Pod' as data_source,
        li.namespace,
        li.pod,
        li.node,
        li.pod_labels,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(m.unit_of_measure) as unit_of_measure,
        sum(li.usage_quantity / li.shared_pods) as usage_quantity,
        sum(li.pretax_cost / li.shared_pods) as pretax_cost,
        sum(li.pretax_cost / li.shared_pods) * {{markup}}::numeric as markup_cost,
        max(li.offer_id) as offer_id,
        max(li.shared_pods) as shared_pods,
        li.pod_cost,
        li.pod_cost * {{markup}}::numeric as project_markup_cost,
        ab.provider_id as source_uuid
    FROM reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_date >= {{start_date}}::date
        AND li.usage_date <= {{end_date}}::date
    -- Grouping by OCP this time for the by project view
    GROUP BY li.report_period_id,
        li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.pod_labels,
        li.pod_cost,
        ab.provider_id

    UNION

    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        'Storage' as data_source,
        li.namespace,
        li.pod,
        li.node,
        li.persistentvolume_labels || li.persistentvolumeclaim_labels as pod_labels,
        max(li.usage_date) as usage_start,
        max(li.usage_date) as usage_end,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.subscription_guid) as subscription_guid,
        max(p.service_name) as service_name,
        max(p.additional_info->>'ServiceType') as instance_type,
        max(p.resource_location) as resource_location,
        max(split_part(p.instance_id, '/', 9)) as resource_id,
        max(m.currency) as currency,
        max(m.unit_of_measure) as unit_of_measure,
        sum(li.usage_quantity / li.shared_pods) as usage_quantity,
        sum(li.pretax_cost / li.shared_pods) as pretax_cost,
        sum(li.pretax_cost / li.shared_pods) * {{markup}}::numeric as markup_cost,
        max(li.offer_id) as offer_id,
        max(li.shared_pods) as shared_pods,
        li.pod_cost,
        li.pod_cost * {{markup}}::numeric as project_markup_cost,
        ab.provider_id as source_uuid
    FROM reporting_ocpazurestoragelineitem_daily_{{uuid | sqlsafe}} AS li
JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | sqlsafe}}.reporting_azuremeter as m
        ON li.meter_id = m.id
    LEFT JOIN reporting_ocpazureusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.azure_id = li.azure_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_date >= {{start_date}}::date
        AND li.usage_date <= {{end_date}}::date
        AND ulid.azure_id IS NULL
    GROUP BY li.report_period_id,
        li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels,
        li.pod_cost,
        ab.provider_id
)
;

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
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    pod,
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
    offer_id,
    currency,
    unit_of_measure,
    shared_projects,
    project_costs,
    source_uuid
)
    SELECT report_period_id,
        cluster_id,
        cluster_alias,
        namespace,
        pod,
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
        offer_id,
        currency,
        unit_of_measure,
        shared_projects,
        project_costs,
        source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary_{{uuid | sqlsafe}}
;

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
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    pod,
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
    offer_id,
    currency,
    unit_of_measure,
    pod_cost,
    project_markup_cost,
    source_uuid
)
    SELECT report_period_id,
        cluster_id,
        cluster_alias,
        data_source,
        namespace,
        pod,
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
        offer_id,
        currency,
        unit_of_measure,
        pod_cost,
        project_markup_cost,
        source_uuid
    FROM reporting_ocpazurecostlineitem_project_daily_summary_{{uuid | sqlsafe}}
;
