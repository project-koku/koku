DROP INDEX IF EXISTS ocpallcstdlysumm_node;
DROP INDEX IF EXISTS ocpallcstdlysumm_node_like;
DROP INDEX IF EXISTS ocpallcstdlysumm_nsp;
DROP INDEX IF EXISTS ocpall_product_code_ilike;
DROP INDEX IF EXISTS ocpall_cost_daily_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpallcostlineitem_daily_summary;

CREATE MATERIALIZED VIEW reporting_ocpallcostlineitem_daily_summary AS (
    SELECT row_number() OVER () as id,
        lids.*
    FROM (
        SELECT 'AWS' as source_type,
            cluster_id,
            cluster_alias,
            namespace,
            node::text as node,
            resource_id,
            usage_start,
            usage_end,
            usage_account_id,
            account_alias_id,
            product_code,
            product_family,
            instance_type,
            region,
            availability_zone,
            tags,
            usage_amount,
            unit,
            unblended_cost,
            markup_cost,
            currency_code,
            shared_projects,
            project_costs,
            source_uuid
        FROM reporting_ocpawscostlineitem_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date

        UNION

        SELECT 'Azure' as source_type,
            cluster_id,
            cluster_alias,
            namespace,
            node::text as node,
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
            tags,
            usage_quantity as usage_amount,
            unit_of_measure as unit,
            pretax_cost as unblended_cost,
            markup_cost,
            currency as currency_code,
            shared_projects,
            project_costs,
            source_uuid
        FROM reporting_ocpazurecostlineitem_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    ) AS lids
)
;

CREATE UNIQUE INDEX ocpall_cost_daily_summary
    ON reporting_ocpallcostlineitem_daily_summary (source_type, usage_start, cluster_id, namespace, node, usage_account_id, resource_id, product_code, product_family, instance_type, region, availability_zone, tags)

CREATE INDEX ocpallcstdlysumm_node
    ON reporting_ocpallcostlineitem_daily_summary (node text_pattern_ops);

CREATE INDEX ocpallcstdlysumm_node_like
    ON reporting_ocpallcostlineitem_daily_summary
    USING GIN (node gin_trgm_ops);

CREATE INDEX ocpallcstdlysumm_nsp
    ON reporting_ocpallcostlineitem_daily_summary
    USING GIN (namespace);

CREATE INDEX ocpall_product_code_ilike
    ON reporting_ocpallcostlineitem_daily_summary
    USING GIN (upper(product_code) gin_trgm_ops);
