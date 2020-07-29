DROP INDEX IF EXISTS ocpall_cost_project_daily_summary;
DROP INDEX IF EXISTS ocpallcstprjdlysumm_node;
DROP INDEX IF EXISTS ocpallcstprjdlysumm_nsp;
DROP INDEX IF EXISTS ocpallcstprjdlysumm_node_like;
DROP INDEX IF EXISTS ocpallcstprjdlysumm_nsp_like;
DROP INDEX IF EXISTS ocpall_product_family_ilike;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpallcostlineitem_project_daily_summary;

CREATE MATERIALIZED VIEW reporting_ocpallcostlineitem_project_daily_summary AS (
    SELECT row_number() OVER () as id,
        lids.*
    FROM (
        SELECT 'AWS' as source_type,
            cluster_id,
            max(cluster_alias) as cluster_alias,
            data_source,
            namespace::text as namespace,
            node::text as node,
            pod_labels,
            resource_id,
            usage_start,
            usage_end,
            usage_account_id,
            max(account_alias_id) as account_alias_id,
            product_code,
            product_family,
            instance_type,
            region,
            availability_zone,
            sum(usage_amount) as usage_amount,
            max(unit) as unit,
            sum(unblended_cost) as unblended_cost,
            sum(project_markup_cost) as project_markup_cost,
            sum(pod_cost) as pod_cost,
            max(currency_code) as currency_code,
            max(source_uuid::text)::uuid as source_uuid
        FROM reporting_ocpawscostlineitem_project_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        GROUP BY source_type,
            usage_start,
            usage_end,
            cluster_id,
            data_source,
            namespace,
            node,
            usage_account_id,
            resource_id,
            product_code,
            product_family,
            instance_type,
            region,
            availability_zone,
            pod_labels

        UNION

        SELECT 'Azure' as source_type,
            cluster_id,
            max(cluster_alias) as cluster_alias,
            data_source,
            namespace::text as namespace,
            node::text as node,
            pod_labels,
            resource_id,
            usage_start,
            usage_end,
            subscription_guid as usage_account_id,
            NULL::int as account_alias_id,
            service_name as product_code,
            NULL as product_family,
            instance_type,
            resource_location as region,
            NULL as availability_zone,
            sum(usage_quantity) as usage_amount,
            max(unit_of_measure) as unit,
            sum(pretax_cost) as unblended_cost,
            sum(project_markup_cost) as project_markup_cost,
            sum(pod_cost) as pod_cost,
            max(currency) as currency_code,
            max(source_uuid::text)::uuid as source_uuid
        FROM reporting_ocpazurecostlineitem_project_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        GROUP BY source_type,
            usage_start,
            usage_end,
            cluster_id,
            data_source,
            namespace,
            node,
            usage_account_id,
            resource_id,
            product_code,
            product_family,
            instance_type,
            region,
            availability_zone,
            pod_labels
    ) AS lids
)
;

CREATE UNIQUE INDEX ocpall_cost_project_daily_summary
    ON reporting_ocpallcostlineitem_project_daily_summary (source_type, usage_start, cluster_id, data_source, namespace, node, usage_account_id, resource_id, product_code, product_family, instance_type, region, availability_zone, pod_labels)
;

CREATE INDEX ocpallcstprjdlysumm_node
    ON reporting_ocpallcostlineitem_project_daily_summary (node text_pattern_ops);

CREATE INDEX ocpallcstprjdlysumm_nsp
    ON reporting_ocpallcostlineitem_project_daily_summary (namespace text_pattern_ops);

CREATE INDEX ocpallcstprjdlysumm_node_like
    ON reporting_ocpallcostlineitem_project_daily_summary
    USING GIN (node gin_trgm_ops);

CREATE INDEX ocpallcstprjdlysumm_nsp_like
    ON reporting_ocpallcostlineitem_project_daily_summary
    USING GIN (namespace gin_trgm_ops);

CREATE INDEX ocpall_product_family_ilike
    ON reporting_ocpallcostlineitem_daily_summary
    USING GIN (upper(product_family) gin_trgm_ops);
