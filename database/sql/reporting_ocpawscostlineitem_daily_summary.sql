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
        aws.id as aws_id,
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
        aws.id as aws_id,
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
        aws.id as aws_id,
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
    WITH cte_pod_project_cost AS (
        SELECT pc.aws_id,
            jsonb_object_agg(pc.namespace, pc.pod_cost) as project_costs
        FROM (
            SELECT li.aws_id,
                li.namespace,
                sum((li.pod_usage_cpu_core_seconds / li.node_capacity_cpu_core_seconds) * li.unblended_cost) as pod_cost
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
                max(li.unblended_cost) / max(li.shared_projects) as pod_cost
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
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(p.region) as region,
        max(pr.unit) as unit,
        li.tags,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.namespace) as shared_projects,
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
        max(li.usage_account_id) as usage_account_id,
        max(aa.id) as account_alias_id,
        max(li.availability_zone) as availability_zone,
        max(p.region) as region,
        max(pr.unit) as unit,
        li.tags,
        max(li.usage_amount) as usage_amount,
        max(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.namespace) as shared_projects,
        pc.project_costs
    FROM reporting_ocpawsstoragelineitem_daily_{uuid} as li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN cte_storage_project_cost AS pc
        ON li.aws_id = pc.aws_id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
    GROUP BY li.aws_id, li.tags, pc.project_costs
)
;

CREATE TEMPORARY TABLE reporting_ocpawscostlineitem_project_daily_summary_{uuid} AS (
    SELECT li.cluster_id,
        li.cluster_alias,
        pc.key as namespace,
        li.node,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.product_code,
        li.product_family,
        li.instance_type,
        li.usage_account_id,
        li.account_alias_id,
        li.availability_zone,
        li.region,
        li.unit,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.normalized_usage_amount) as normalized_usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        max(shared_projects) as shared_projects,
        sum(cast(pc.value as numeric(24,6))) as project_cost
    FROM reporting_ocpawscostlineitem_daily_summary_{uuid} li,
        jsonb_each_text(li.project_costs) pc
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
    GROUP BY li.cluster_id,
        li.cluster_alias,
        pc.key,
        li.node,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.product_code,
        li.product_family,
        li.instance_type,
        li.usage_account_id,
        li.account_alias_id,
        li.availability_zone,
        li.region,
        li.unit,
        li.tags
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpawscostlineitem_daily_summary
WHERE date(usage_start) >= '{start_date}'
    AND date(usage_start) <= '{end_date}'
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
;

INSERT INTO reporting_ocpawscostlineitem_project_daily_summary (
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
    project_cost
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        node,
        resource_id,
        usage_start,
        usage_end,
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
        project_cost
    FROM reporting_ocpawscostlineitem_project_daily_summary_{uuid}
