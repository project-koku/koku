CREATE TEMPORARY TABLE reporting_ocpawsstoragelineitem_daily_{uuid} AS (
    WITH cte_storage_tag_matchted as (
        SELECT aws.id as aws_id,
                COALESCE(pvl.id, pvcl.id) as ocp_id,
                aws.usage_start,
                COALESCE(pvl.namespace, pvcl.namespace) as namespace
            FROM (
            SELECT aws.id,
                aws.usage_start,
                LOWER(key) as key,
                LOWER(value) as value
                FROM reporting_awscostentrylineitem_daily as aws,
                    jsonb_each_text(aws.tags) labels
                WHERE date(aws.usage_start) >= '{start_date}'
                    AND date(aws.usage_start) <= '{end_date}'
            ) AS aws
            LEFT JOIN (
                SELECT ocp.id,
                    ocp.usage_start,
                    ocp.cluster_alias,
                    ocp.node,
                    ocp.namespace,
                    LOWER(key) as key,
                    LOWER(value) as value
                FROM reporting_ocpstoragelineitem_daily as ocp,
                    jsonb_each_text(ocp.persistentvolume_labels) labels
                WHERE date(ocp.usage_start) >= '{start_date}'
                    AND date(ocp.usage_start) <= '{end_date}'
            ) AS pvl
                ON aws.usage_start::date = pvl.usage_start::date
                    AND (
                        (aws.key = pvl.key AND aws.value = pvl.value)
                        OR (aws.key = 'openshift_cluster' AND aws.value = pvl.cluster_alias)
                        OR (aws.key = 'openshift_node' AND aws.value = pvl.node)
                        OR (aws.key = 'openshift_project' AND aws.value = pvl.namespace)
                    )
            LEFT JOIN (
                SELECT ocp.id,
                    ocp.usage_start,
                    ocp.cluster_alias,
                    ocp.node,
                    ocp.namespace,
                    LOWER(key) as key,
                    LOWER(value) as value
                FROM reporting_ocpstoragelineitem_daily as ocp,
                    jsonb_each_text(ocp.persistentvolumeclaim_labels) labels
                WHERE date(ocp.usage_start) >= '{start_date}'
                    AND date(ocp.usage_start) <= '{end_date}'
        ) AS pvcl
                ON aws.usage_start::date = pvcl.usage_start::date
                    AND (
                        (aws.key = pvcl.key AND aws.value = pvcl.value)
                        OR (aws.key = 'openshift_cluster' AND aws.value = pvcl.cluster_alias)
                        OR (aws.key = 'openshift_node' AND aws.value = pvcl.node)
                        OR (aws.key = 'openshift_project' AND aws.value = pvcl.namespace)
                    )
        WHERE (pvl.id IS NOT NULL OR pvcl.id IS NOT NULL)
            OR pvl.id = pvcl.id
        GROUP BY aws.usage_start, aws.id, pvl.id, pvcl.id, pvl.namespace, pvcl.namespace
    ),
    cte_number_of_shared_projects AS (
        SELECT usage_start,
            aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_storage_tag_matchted
        GROUP BY usage_start, aws_id
    )
    SELECT ocp.cluster_id,
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
        aws.tags,
        tm.shared_projects
    FROM (
        SELECT tm.usage_start,
            tm.ocp_id,
            tm.aws_id,
            max(sp.shared_projects) as shared_projects
        FROM cte_storage_tag_matchted AS tm
        LEFT JOIN cte_number_of_shared_projects AS sp
            ON tm.aws_id = sp.aws_id
        GROUP BY tm.usage_start, tm.ocp_id, tm.aws_id
    ) AS tm
    JOIN reporting_awscostentrylineitem_daily as aws
        ON tm.aws_id = aws.id
    JOIN reporting_ocpstoragelineitem_daily as ocp
        ON tm.ocp_id = ocp.id
)
;

CREATE TEMPORARY TABLE reporting_ocpawsusagelineitem_daily_{uuid} AS (
    WITH cte_usage_tag_matched as (
        SELECT aws.id as aws_id,
                ocp.id as ocp_id,
                aws.usage_start,
                ocp.namespace
            FROM (
            SELECT aws.id,
                aws.usage_start,
                LOWER(key) as key,
                LOWER(value) as value
                FROM reporting_awscostentrylineitem_daily as aws,
                    jsonb_each_text(aws.tags) labels
                WHERE date(aws.usage_start) >= '{start_date}'
                    AND date(aws.usage_start) <= '{end_date}'
            ) AS aws
            JOIN (
                SELECT ocp.id,
                    ocp.usage_start,
                    ocp.cluster_alias,
                    ocp.node,
                    ocp.namespace,
                    LOWER(key) as key,
                    LOWER(value) as value
                FROM reporting_ocpusagelineitem_daily as ocp,
                    jsonb_each_text(ocp.pod_labels) labels
                WHERE date(ocp.usage_start) >= '{start_date}'
                    AND date(ocp.usage_start) <= '{end_date}'
            ) AS ocp
                ON aws.usage_start::date = ocp.usage_start::date
                    AND (
                        (aws.key = ocp.key AND aws.value = ocp.value)
                        OR (aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_alias)
                        OR (aws.key = 'openshift_node' AND aws.value = ocp.node)
                        OR (aws.key = 'openshift_project' AND aws.value = ocp.namespace)
                    )
            GROUP BY aws.id, ocp.id, aws.usage_start, ocp.namespace
    ),
    cte_number_of_shared_projects AS (
        SELECT usage_start,
            aws_id,
            count(DISTINCT namespace) as shared_projects
        FROM cte_usage_tag_matched
        GROUP BY usage_start, aws_id
    )
    SELECT ocp.cluster_id,
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
        aws.tags,
        1::int as shared_projects
    FROM reporting_awscostentrylineitem_daily as aws
    JOIN reporting_ocpusagelineitem_daily as ocp
        ON aws.resource_id = ocp.resource_id
            AND aws.usage_start::date = ocp.usage_start::date
    WHERE date(aws.usage_start) >= '{start_date}'
        AND date(aws.usage_start) <= '{end_date}'

    UNION

    SELECT ocp.cluster_id,
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
        aws.tags,
        tm.shared_projects
    FROM (
        SELECT tm.usage_start,
            tm.ocp_id,
            tm.aws_id,
            max(sp.shared_projects) as shared_projects
        FROM cte_usage_tag_matched AS tm
        LEFT JOIN cte_number_of_shared_projects AS sp
            ON tm.aws_id = sp.aws_id
        GROUP BY tm.usage_start, tm.ocp_id, tm.aws_id
    ) AS tm
    JOIN reporting_awscostentrylineitem_daily as aws
        ON tm.aws_id = aws.id
    JOIN reporting_ocpusagelineitem_daily as ocp
        ON tm.ocp_id = ocp.id
);

-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_daily_summary_{uuid} AS (
    SELECT li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.pod_labels as openshift_labels,
        li.product_code,
        p.product_family,
        p.instance_type,
        li.usage_account_id,
        aa.id as account_alias_id,
        li.availability_zone,
        p.region,
        pr.unit,
        li.tags,
        li.usage_amount,
        li.normalized_usage_amount,
        li.unblended_cost,
        li.shared_projects,
        (li.pod_usage_cpu_core_seconds / li.node_capacity_cpu_core_seconds) *
            li.unblended_cost as pod_cost
    FROM reporting_ocpawsusagelineitem_daily_{uuid} as li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= '{start_date}'
        AND li.usage_start <= '{end_date}'

    UNION

    SELECT li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.persistentvolume_labels || li.persistentvolumeclaim_labels as openshift_labels,
        li.product_code,
        p.product_family,
        p.instance_type,
        li.usage_account_id,
        aa.id as account_alias_id,
        li.availability_zone,
        p.region,
        pr.unit,
        li.tags,
        li.usage_amount,
        li.normalized_usage_amount,
        li.unblended_cost,
        li.shared_projects,
        li.unblended_cost / li.shared_projects as pod_cost
    FROM reporting_ocpawsstoragelineitem_daily_{uuid} as li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= '{start_date}'
        AND li.usage_start <= '{end_date}'
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpawscostlineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
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
    openshift_labels,
    product_code,
    product_family,
    instance_type,
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
    pod_cost
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
        node,
        resource_id,
        usage_start,
        usage_end,
        openshift_labels,
        product_code,
        product_family,
        instance_type,
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
        pod_cost
    FROM reporting_ocpawscostlineitem_daily_summary_{uuid}
;
