DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND cluster_id = {{cluster_id}}
    AND infrastructure_raw_cost IS NOT NULL
;

-- The Python Jinja string variable subsitutions aws_where_clause and ocp_where_clause
-- optionally filter AWS and OCP data by provider/source
-- Ex aws_where_clause: 'AND cost_entry_bill_id IN (1, 2, 3)'
-- Ex ocp_where_clause: "AND cluster_id = 'abcd-1234`"
CREATE TEMPORARY TABLE matched_tags_{{uuid | sqlsafe}} AS (
    WITH cte_unnested_aws_tags AS (
        SELECT tags.*,
            b.billing_period_start
        FROM (
            SELECT key,
                value,
                cost_entry_bill_id
            FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts,
                unnest(ts.values) AS values(value)
        ) AS tags
        JOIN {{schema | sqlsafe}}.reporting_awscostentrybill AS b
            ON tags.cost_entry_bill_id = b.id
        JOIN {{schema | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
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
                report_period_id
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
                report_period_id
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

-- Selects the data from aws daily and includes only
-- the enabled tags in the results
CREATE TEMPORARY TABLE reporting_aws_with_enabled_tags_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM {{schema | sqlsafe}}.reporting_awsenabledtagkeys
    ),
    cte_filtered_aws_tags AS (
        SELECT id,
            jsonb_object_agg(key,value) as aws_tags
        FROM (
            SELECT lid.id,
                lid.tags as aws_tags,
                aak.key_array
            FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.tags ?| aak.key_array
                AND lid.usage_start >= {{start_date}}::date
                AND lid.usage_start <= {{end_date}}::date
                {% if bill_ids %}
                AND lid.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids  -%}
                        {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%})
                {% endif %}
        ) AS lid,
        jsonb_each_text(lid.aws_tags) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    )
    SELECT aws.id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            fvl.aws_tags as tags
        FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily as aws
        LEFT JOIN cte_filtered_aws_tags as fvl
            ON aws.id = fvl.id
)
;
-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_aws_tags_{{uuid | sqlsafe}} AS (
    SELECT aws.*
    FROM (
        SELECT aws.*,
            lower(aws.tags::text)::jsonb as lower_tags,
            row_number() OVER (PARTITION BY aws.id ORDER BY aws.id) as row_number
            FROM reporting_aws_with_enabled_tags_{{uuid | sqlsafe}} as aws
            JOIN matched_tags_{{uuid | sqlsafe}} as tag
                ON aws.cost_entry_bill_id = tag.cost_entry_bill_id
                    AND aws.tags @> tag.tag
            WHERE aws.usage_start >= {{start_date}}::date
                AND aws.usage_start <= {{end_date}}::date
                --aws_where_clause
                {% if bill_ids %}
                AND aws.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%}
                )
                {% endif %}
    ) AS aws
    WHERE aws.row_number = 1
)
;

DROP INDEX IF EXISTS aws_tags_gin_idx
;
CREATE INDEX aws_tags_gin_idx ON reporting_aws_tags_{{uuid | sqlsafe}} USING GIN (lower_tags)
;

CREATE TEMPORARY TABLE reporting_aws_special_case_tags_{{uuid | sqlsafe}} AS (
    WITH cte_tag_options AS (
        SELECT jsonb_build_object(key, value) as tag,
            lower(key) as key,
            lower(value) as value,
            cost_entry_bill_id
        FROM (
            SELECT key,
                value,
                ts.cost_entry_bill_id
            FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts,
                unnest(values) AS values(value)
            --aws_where_clause
            {% if bill_ids %}
            WHERE ts.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
        ) AS keyval
        WHERE lower(key) IN ('openshift_cluster', 'openshift_node', 'openshift_project')
    )
    SELECT aws.*,
        lower(tag.key) as key,
        lower(tag.value) as value
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily as aws
    JOIN cte_tag_options as tag
            ON aws.cost_entry_bill_id = tag.cost_entry_bill_id
                AND aws.tags @> tag.tag
    WHERE aws.usage_start >= {{start_date}}::date
        AND aws.usage_start <= {{end_date}}::date
        --aws_where_clause
        {% if bill_ids %}
        AND aws.cost_entry_bill_id IN (
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


-- First we match OCP pod data to AWS data using a direct
-- resource id match. This usually means OCP node -> AWS EC2 instance ID.
CREATE TEMPORARY TABLE reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_with_enabled_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.resource_id = ocp.resource_id
                AND aws.usage_start = ocp.usage_start
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Pod'
            -- aws_where_clause
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
INSERT INTO reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.key = 'openshift_project' AND aws.value = lower(ocp.namespace)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
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
)
;

-- Next we match where the AWS tag is the special openshift_node key
-- and the value matches an OpenShift node name
INSERT INTO reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.key = 'openshift_node' AND aws.value = lower(ocp.node)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
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
)
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON (aws.key = 'openshift_cluster' AND aws.value = lower(ocp.cluster_id)
                OR aws.key = 'openshift_cluster' AND aws.value = lower(ocp.cluster_alias))
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
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
)
;

-- Next we match where the pod label key and value
-- and AWS tag key and value match directly
 INSERT INTO reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_tags_{{uuid | sqlsafe}} as aws
        JOIN reporting_ocp_pod_tags_{{uuid | sqlsafe}} as ocp
            ON aws.lower_tags @> ocp.tag
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
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
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_ocp_pod_tags_{{uuid | sqlsafe}};


-- First we match where the AWS tag is the special openshift_project key
-- and the value matches an OpenShift project name
CREATE TEMPORARY TABLE reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.key = 'openshift_project' AND aws.value = lower(ocp.namespace)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND ulid.aws_id IS NULL

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
INSERT INTO reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON aws.key = 'openshift_node' AND aws.value = lower(ocp.node)
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.aws_id = aws.id
        LEFT JOIN reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND ulid.aws_id IS NULL
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
)
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
 INSERT INTO reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_special_case_tags_{{uuid | sqlsafe}} as aws
        JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
            ON (aws.key = 'openshift_cluster' AND aws.value = lower(ocp.cluster_id)
                OR aws.key = 'openshift_cluster' AND aws.value = lower(ocp.cluster_alias))
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.aws_id = aws.id
        LEFT JOIN reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ocp.usage_start >= {{start_date}}::date
            AND ocp.usage_start <= {{end_date}}::date
            AND ocp.data_source = 'Storage'
            AND ulid.aws_id IS NULL
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
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_aws_special_case_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_aws_special_case_tags_{{uuid | sqlsafe}};


-- Then we match for OpenShift volume data where the volume label key and value
-- and AWS tag key and value match directly
 INSERT INTO reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} (
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
            aws.id AS aws_id,
            aws.cost_entry_bill_id,
            aws.cost_entry_product_id,
            aws.cost_entry_pricing_id,
            aws.cost_entry_reservation_id,
            aws.line_item_type,
            aws.usage_account_id,
            aws.usage_start,
            aws.usage_end,
            aws.product_code,
            aws.usage_type,
            aws.operation,
            aws.availability_zone,
            aws.resource_id,
            aws.usage_amount,
            aws.normalization_factor,
            aws.normalized_usage_amount,
            aws.currency_code,
            aws.unblended_rate,
            aws.unblended_cost,
            aws.blended_rate,
            aws.blended_cost,
            aws.public_on_demand_cost,
            aws.public_on_demand_rate,
            aws.tax_type,
            aws.tags
        FROM reporting_aws_tags_{{uuid | sqlsafe}} as aws
        JOIN reporting_ocp_storage_tags_{{uuid | sqlsafe}} as ocp
            ON aws.lower_tags @> ocp.tag
                AND aws.usage_start = ocp.usage_start
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
            ON ulid.aws_id = aws.id
        LEFT JOIN reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS rm
            ON rm.aws_id = aws.id
        WHERE aws.usage_start >= {{start_date}}::date
            AND aws.usage_start <= {{end_date}}::date
            AND ulid.aws_id IS NULL
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
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_ocp_storage_tags_{{uuid | sqlsafe}};

TRUNCATE TABLE reporting_aws_tags_{{uuid | sqlsafe}};
DROP TABLE reporting_aws_tags_{{uuid | sqlsafe}};


-- The full summary data for Openshift pod<->AWS and
-- Openshift volume<->AWS matches are UNIONed together
-- with a GROUP BY using the AWS ID to deduplicate
-- the AWS data. This should ensure that we never double count
-- AWS cost or usage.
CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_pod_project_cost AS (
        SELECT pc.aws_id,
            jsonb_object_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.aws_id, li.namespace
        ) AS pc
        GROUP BY pc.aws_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.aws_id,
            jsonb_object_agg(pc.namespace, pc.project_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum(project_cost) as project_cost
            FROM reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} as li
            GROUP BY li.aws_id, li.namespace
        ) AS pc
        GROUP BY pc.aws_id
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
        max(li.resource_id) as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(p.product_family) as product_family,
        max(p.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(p.region) as region,
        max(pr.unit) as unit,
        li.tags,
        jsonb_agg(distinct li.pod_labels) as pod_labels,
        count(distinct li.pod_labels) as pod_label_count,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_cost) as unblended_cost,
        max(li.unblended_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} as li
    JOIN {{schema | sqlsafe}}.reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN cte_pod_project_cost as pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awscostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_start >= {{start_date}}::date
        AND li.usage_start <= {{end_date}}::date
    -- Dedup on AWS line item so we never double count usage or cost
    GROUP BY li.aws_id, li.tags, pc.project_costs, ab.provider_id

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
        max(li.resource_id) as resource_id,
        max(li.usage_start) as usage_start,
        max(li.usage_end) as usage_end,
        max(li.product_code) as product_code,
        max(p.product_family) as product_family,
        max(p.instance_type) as instance_type,
        max(li.cost_entry_bill_id) as cost_entry_bill_id,
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(p.region) as region,
        max(pr.unit) as unit,
        li.tags,
        jsonb_agg(distinct li.volume_labels) as pod_labels,
        count(distinct li.volume_labels) as pod_label_count,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_cost) as unblended_cost,
        max(li.unblended_cost) * {{markup}}::numeric as markup_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs,
        ab.provider_id as source_uuid
    FROM reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}} AS li
    JOIN {{schema | sqlsafe}}.reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN cte_storage_project_cost AS pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}} AS ulid
        ON ulid.aws_id = li.aws_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awscostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_start >= {{start_date}}::date
        AND li.usage_start <= {{end_date}}::date
        AND ulid.aws_id IS NULL
    GROUP BY li.aws_id, li.tags, pc.project_costs, ab.provider_id
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
CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.data_source,
        project as "namespace",
        li.node,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        pod_label as pod_labels,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.product_code,
        li.product_family,
        li.instance_type,
        li.cost_entry_bill_id,
        li.usage_account_id,
        li.account_alias_id,
        li.availability_zone,
        li.region,
        li.unit,
        li.currency_code,
        li.usage_amount / li.pod_label_count / li.shared_projects as usage_amount,
        li.normalized_usage_amount / li.pod_label_count / li.shared_projects as normalized_usage_amount,
        li.unblended_cost / li.pod_label_count / li.shared_projects as unblended_cost,
        li.unblended_cost / li.pod_label_count / li.shared_projects * {{markup}}::numeric as markup_cost,
        project_cost::numeric as project_cost,
        project_cost::numeric * {{markup}}::numeric as project_markup_cost,
        li.source_uuid
    FROM reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}} as li,
        jsonb_array_elements(li.pod_labels) AS pod_labels(pod_label),
        jsonb_each_text(li.project_costs) AS project_costs(project, project_cost)
)
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpawsusagelineitem_daily_{{uuid | sqlsafe}};

TRUNCATE TABLE reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpawsstoragelineitem_daily_{{uuid | sqlsafe}};


-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    --aws_where_clause
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
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary (
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
    SELECT uuid_generate_v4(),
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
    FROM reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}}
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpawscostlineitem_daily_summary_{{uuid | sqlsafe}};


DELETE FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    --aws_where_clause
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

INSERT INTO {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary (
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
        project_cost,
        project_markup_cost,
        source_uuid
    FROM reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}}
;

DROP INDEX IF EXISTS aws_tags_gin_idx;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpawscostlineitem_project_daily_summary_{{uuid | sqlsafe}};

-- Update infra raw costs in OCP table
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND cluster_id = {{cluster_id}}
    AND infrastructure_raw_cost IS NOT NULL
;

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
        ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        max(ocp_aws.persistentvolume),
        max(ocp_aws.storageclass),
        ocp_aws.resource_id,
        CASE WHEN ocp_aws.data_source = 'Pod'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_aws.data_source = 'Storage'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        rp.provider_id as source_uuid,
        sum(ocp_aws.unblended_cost + ocp_aws.markup_cost) AS infrastructure_raw_cost,
        sum(ocp_aws.pod_cost + ocp_aws.project_markup_cost) AS infrastructure_project_raw_cost,
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
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_aws.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_aws.usage_start)::date  = date(rp.report_period_start)
    WHERE ocp_aws.usage_start >= {{start_date}}::date
        AND ocp_aws.usage_start <= {{end_date}}::date
        AND ocp_aws.cluster_id = {{cluster_id}}
    GROUP BY ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        ocp_aws.resource_id,
        ocp_aws.pod_labels,
        rp.provider_id
;
