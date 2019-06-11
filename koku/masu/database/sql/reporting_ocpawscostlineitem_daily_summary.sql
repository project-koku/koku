-- The Python string variable subsitutions {aws_where_clause} and
-- {ocp_where_clause} optionally filter AWS and OCP data by provider/source
-- Ex aws_where_clause: 'AND cost_entry_bill_id IN (1, 2, 3)'
-- Ex ocp_where_clause: "AND cluster_id = 'abcd-1234`"

-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_aws_tags AS (
    SELECT aws.*,
        LOWER(key) as key,
        LOWER(value) as value
        FROM reporting_awscostentrylineitem_daily as aws,
            jsonb_each_text(aws.tags) labels
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            {aws_where_clause}
)
;

-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_ocp_storage_tags AS (
    SELECT ocp.*,
        LOWER(key) as key,
        LOWER(value) as value
    FROM reporting_ocpstoragelineitem_daily as ocp,
        jsonb_each_text(ocp.persistentvolume_labels) labels
    WHERE date(ocp.usage_start) >= '{start_date}'
        AND date(ocp.usage_start) <= '{end_date}'
        {ocp_where_clause}

    UNION ALL

    SELECT ocp.*,
        LOWER(key) as key,
        LOWER(value) as value
    FROM reporting_ocpstoragelineitem_daily as ocp,
        jsonb_each_text(ocp.persistentvolumeclaim_labels) labels
    WHERE date(ocp.usage_start) >= '{start_date}'
        AND date(ocp.usage_start) <= '{end_date}'
        {ocp_where_clause}
)
;

-- We use a LATERAL JOIN here to get the JSON tags split out into key, value
-- columns. We reference this split multiple times so we put it in a
-- TEMPORARY TABLE for re-use
CREATE TEMPORARY TABLE reporting_ocp_pod_tags AS (
    SELECT ocp.*,
        LOWER(key) as key,
        LOWER(value) as value
    FROM reporting_ocpusagelineitem_daily as ocp,
        jsonb_each_text(ocp.pod_labels) labels
    WHERE date(ocp.usage_start) >= '{start_date}'
        AND date(ocp.usage_start) <= '{end_date}'
        {ocp_where_clause}
)
;

-- First we match OCP pod data to AWS data using a direct
-- resource id match. This usually means OCP node -> AWS EC2 instance ID.
CREATE TEMPORARY TABLE reporting_ocp_aws_resource_id_matched AS (
    WITH cte_resource_id_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_awscostentrylineitem_daily as aws
        JOIN reporting_ocpusagelineitem_daily as ocp
            ON aws.resource_id = ocp.resource_id
                AND aws.usage_start::date = ocp.usage_start::date
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_resource_id_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_resource_id_matched
        GROUP BY aws_id
    )
    SELECT rm.*,
        (rm.pod_usage_cpu_core_seconds / rm.node_capacity_cpu_core_seconds) * rm.unblended_cost as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_resource_id_matched AS rm
    JOIN cte_number_of_shared_projects AS sp
        ON rm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON rm.aws_id = spod.aws_id

)
;

-- Next we match where the pod label key and value
-- and AWS tag key and value match directly
CREATE TEMPORARY TABLE reporting_ocp_aws_direct_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_pod_tags as ocp
            ON aws.key = ocp.key
                AND aws.value = ocp.value
                AND aws.usage_start::date = ocp.usage_start::date
        LEFT JOIN reporting_ocp_aws_resource_id_matched AS rm
            ON rm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND rm.aws_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_project key
-- and the value matches an OpenShift project name
CREATE TEMPORARY TABLE reporting_ocp_aws_openshift_project_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_pod_tags as ocp
            ON aws.key = 'openshift_project' AND aws.value = ocp.namespace
                AND aws.usage_start::date = ocp.usage_start::date
        LEFT JOIN reporting_ocp_aws_resource_id_matched AS rm
            ON rm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND rm.aws_id IS NULL
            AND dtm.aws_id IS NULL

    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_node key
-- and the value matches an OpenShift node name
CREATE TEMPORARY TABLE reporting_ocp_aws_openshift_node_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_pod_tags as ocp
            ON aws.key = 'openshift_node' AND aws.value = ocp.node
                AND aws.usage_start::date = ocp.usage_start::date
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_aws_resource_id_matched AS rm
            ON rm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_openshift_project_tag_matched as ptm
            ON ptm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND rm.aws_id IS NULL
            AND dtm.aws_id IS NULL
            AND ptm.aws_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
CREATE TEMPORARY TABLE reporting_ocp_aws_openshift_cluster_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_pod_tags as ocp
            ON (aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_id
                OR aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_alias)
                AND aws.usage_start::date = ocp.usage_start::date
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_aws_resource_id_matched AS rm
            ON rm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_openshift_project_tag_matched as ptm
            ON ptm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_openshift_node_tag_matched as ntm
            ON ntm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND rm.aws_id IS NULL
            AND dtm.aws_id IS NULL
            AND ptm.aws_id IS NULL
            AND ntm.aws_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- We UNION the various matches into a table holding all of the
-- OpenShift pod data matches for easier use.
CREATE TEMPORARY TABLE reporting_ocpawsusagelineitem_daily_{uuid} AS (
    SELECT *
    FROM reporting_ocp_aws_resource_id_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_direct_tag_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_openshift_project_tag_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_openshift_node_tag_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_openshift_cluster_tag_matched
);

-- Then we match for OpenShift volume data where the volume label key and value
-- and AWS tag key and value match directly
CREATE TEMPORARY TABLE reporting_ocp_aws_storage_direct_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_storage_tags as ocp
            ON aws.key = ocp.key
                AND aws.value = ocp.value
                AND aws.usage_start::date = ocp.usage_start::date
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Then we match where the AWS tag is the special openshift_project key
-- and the value matches an OpenShift project name
CREATE TEMPORARY TABLE reporting_ocp_aws_storage_openshift_project_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_storage_tags as ocp
            ON aws.key = 'openshift_project' AND aws.value = ocp.namespace
                AND aws.usage_start::date = ocp.usage_start::date
        LEFT JOIN reporting_ocp_aws_storage_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND dtm.aws_id IS NULL

    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_node key
-- and the value matches an OpenShift node name
CREATE TEMPORARY TABLE reporting_ocp_aws_storage_openshift_node_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_storage_tags as ocp
            ON aws.key = 'openshift_node' AND aws.value = ocp.node
                AND aws.usage_start::date = ocp.usage_start::date
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_aws_storage_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_storage_openshift_project_tag_matched as ptm
            ON ptm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND dtm.aws_id IS NULL
            AND ptm.aws_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- Next we match where the AWS tag is the special openshift_cluster key
-- and the value matches an OpenShift cluster name
CREATE TEMPORARY TABLE reporting_ocp_aws_storage_openshift_cluster_tag_matched AS (
    WITH cte_tag_matched AS (
        SELECT ocp.id AS ocp_id,
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
        FROM reporting_aws_tags as aws
        JOIN reporting_ocp_storage_tags as ocp
            ON (aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_id
                OR aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_alias)
                AND aws.usage_start::date = ocp.usage_start::date
        -- ANTI JOIN to remove rows that already matched
        LEFT JOIN reporting_ocp_aws_storage_direct_tag_matched AS dtm
            ON dtm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_storage_openshift_project_tag_matched as ptm
            ON ptm.aws_id = aws.id
        LEFT JOIN reporting_ocp_aws_storage_openshift_node_tag_matched as ntm
            ON ntm.aws_id = aws.id
        WHERE date(aws.usage_start) >= '{start_date}'
            AND date(aws.usage_start) <= '{end_date}'
            AND dtm.aws_id IS NULL
            AND ptm.aws_id IS NULL
            AND ntm.aws_id IS NULL
    ),
    cte_number_of_shared_projects AS (
        SELECT aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_tag_matched
        GROUP BY aws_id
    ),
    cte_number_of_shared_pods AS (
        SELECT aws_id,
            count(DISTINCT pod) as shared_pods
        FROM cte_tag_matched
        GROUP BY aws_id
    )
    SELECT tm.*,
        tm.unblended_cost / spod.shared_pods as pod_cost,
        sp.shared_projects,
        spod.shared_pods
    FROM cte_tag_matched AS tm
    JOIN cte_number_of_shared_projects AS sp
        ON tm.aws_id = sp.aws_id
    JOIN cte_number_of_shared_pods AS spod
        ON tm.aws_id = spod.aws_id
)
;

-- We UNION the various matches into a table holding all of the
-- OpenShift volume data matches for easier use.
CREATE TEMPORARY TABLE reporting_ocpawsstoragelineitem_daily_{uuid} AS (
    SELECT *
    FROM reporting_ocp_aws_storage_direct_tag_matched

    UNION


    SELECT *
    FROM reporting_ocp_aws_storage_openshift_project_tag_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_storage_openshift_node_tag_matched

    UNION

    SELECT *
    FROM reporting_ocp_aws_storage_openshift_cluster_tag_matched
);

-- The full summary data for Openshift pod<->AWS and
-- Openshift volume<->AWS matches are UNIONed together
-- with a GROUP BY using the AWS ID to deduplicate
-- the AWS data. This should ensure that we never double count
-- AWS cost or usage.
CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_daily_summary_{uuid} AS (
    WITH cte_pod_project_cost AS (
        SELECT pc.aws_id,
            jsonb_object_agg(pc.namespace, pc.pod_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum(pod_cost) as pod_cost
            FROM reporting_ocpawsusagelineitem_daily_{uuid} as li
            GROUP BY li.aws_id, li.namespace
        ) AS pc
        GROUP BY pc.aws_id
    ),
    cte_storage_project_cost AS (
        SELECT pc.aws_id,
            jsonb_object_agg(pc.namespace, pc.pod_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum(pod_cost) as pod_cost
            FROM reporting_ocpawsstoragelineitem_daily_{uuid} as li
            GROUP BY li.aws_id, li.namespace
        ) AS pc
        GROUP BY pc.aws_id
    )
    SELECT max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        array_agg(DISTINCT li.pod) as pod,
        max(li.node) as node,
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
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.unblended_cost) as unblended_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs as project_costs
    FROM reporting_ocpawsusagelineitem_daily_{uuid} as li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN cte_pod_project_cost as pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
    -- Dedup on AWS line item so we never double count usage or cost
    GROUP BY li.aws_id, li.tags, pc.project_costs

    UNION

    SELECT max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias,
        array_agg(DISTINCT li.namespace) as namespace,
        array_agg(DISTINCT li.pod) as pod,
        max(li.node) as node,
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
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.unblended_cost) as unblended_cost,
        max(li.shared_projects) as shared_projects,
        pc.project_costs
    FROM reporting_ocpawsstoragelineitem_daily_{uuid} AS li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN cte_storage_project_cost AS pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN reporting_ocpawsusagelineitem_daily_{uuid} AS ulid
        ON ulid.aws_id = li.aws_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
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
CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_project_daily_summary_{uuid} AS (
    SELECT li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.pod_labels,
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
        sum(li.usage_amount / li.shared_pods) as usage_amount,
        sum(li.normalized_usage_amount / li.shared_pods) as normalized_usage_amount,
        sum(li.unblended_cost / li.shared_pods) as unblended_cost,
        max(li.shared_pods) as shared_pods,
        li.pod_cost
    FROM reporting_ocpawsusagelineitem_daily_{uuid} as li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
    -- Grouping by OCP this time for the by project view
    GROUP BY li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.pod_labels,
        li.pod_cost

    UNION

    SELECT li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.persistentvolume_labels || li.persistentvolumeclaim_labels as pod_labels,
        NULL as resource_id,
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
        sum(li.usage_amount / li.shared_pods) as usage_amount,
        sum(li.normalized_usage_amount / li.shared_pods) as normalized_usage_amount,
        sum(li.unblended_cost / li.shared_pods) as unblended_cost,
        max(li.shared_pods) as shared_pods,
        li.pod_cost
    FROM reporting_ocpawsstoragelineitem_daily_{uuid} AS li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN reporting_ocpawsusagelineitem_daily_{uuid} AS ulid
        ON ulid.aws_id = li.aws_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
        AND ulid.aws_id IS NULL
    GROUP BY li.ocp_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels,
        li.pod_cost
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpawscostlineitem_daily_summary
WHERE date(usage_start) >= '{start_date}'
    AND date(usage_start) <= '{end_date}'
    {aws_where_clause}
    {ocp_where_clause}
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpawscostlineitem_daily_summary (
    cluster_id,
    cluster_alias,
    namespace,
    pod,
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
    unblended_cost,
    shared_projects,
    project_costs
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
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
        unblended_cost,
        shared_projects,
        project_costs
    FROM reporting_ocpawscostlineitem_daily_summary_{uuid}
;

DELETE FROM reporting_ocpawscostlineitem_project_daily_summary
WHERE date(usage_start) >= '{start_date}'
    AND date(usage_start) <= '{end_date}'
    {aws_where_clause}
    {ocp_where_clause}
;

INSERT INTO reporting_ocpawscostlineitem_project_daily_summary (
    cluster_id,
    cluster_alias,
    namespace,
    pod,
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
    unblended_cost,
    pod_cost
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
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
        unblended_cost,
        pod_cost
    FROM reporting_ocpawscostlineitem_project_daily_summary_{uuid}
