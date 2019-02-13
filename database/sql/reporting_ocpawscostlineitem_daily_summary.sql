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
        li.pod_labels,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        aa.id as account_alias_id,
        li.availability_zone,
        p.region,
        pr.unit,
        li.tags,
        li.usage_amount,
        li.normalized_usage_amount,
        li.unblended_cost,
        (li.pod_usage_cpu_core_seconds / li.node_capacity_cpu_core_seconds) *
            li.unblended_cost as pod_cost
    FROM reporting_ocpawscostlineitem_daily as li
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
    pod_labels,
    product_code,
    product_family,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    tags,
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
        resource_id,
        usage_start,
        usage_end,
        pod_labels,
        product_code,
        product_family,
        usage_account_id,
        account_alias_id,
        availability_zone,
        region,
        unit,
        tags,
        usage_amount,
        normalized_usage_amount,
        unblended_cost,
        pod_cost
    FROM reporting_ocpawscostlineitem_daily_summary_{uuid}
;
