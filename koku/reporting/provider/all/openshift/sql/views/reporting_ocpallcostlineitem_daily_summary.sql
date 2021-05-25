-- Materialized View Create Script : reporting_ocpallcostlineitem_daily_summary
DROP INDEX IF EXISTS ocpall_cost_daily_summary;
DROP INDEX IF EXISTS ocpall_product_code_ilike;
DROP INDEX IF EXISTS ocpall_product_family_ilike;
DROP INDEX IF EXISTS ocpallcstdlysumm_node;
DROP INDEX IF EXISTS ocpallcstdlysumm_node_like;
DROP INDEX IF EXISTS ocpallcstdlysumm_nsp;

DROP MATERIALIZED VIEW IF EXISTS reporting_ocpallcostlineitem_daily_summary;

CREATE MATERIALIZED VIEW reporting_ocpallcostlineitem_daily_summary AS (
    SELECT row_number() OVER () AS id,
        lids.source_type,
        lids.cluster_id,
        max(lids.cluster_alias) as cluster_alias,
        lids.namespace,
        lids.node,
        lids.resource_id,
        lids.usage_start,
        lids.usage_start as usage_end,
        lids.usage_account_id,
        max(lids.account_alias_id) as account_alias_id,
        lids.product_code,
        lids.product_family,
        lids.instance_type,
        lids.region,
        lids.availability_zone,
        lids.tags,
        sum(lids.usage_amount) as usage_amount,
        max(lids.unit) as unit,
        sum(lids.unblended_cost) as unblended_cost,
        sum(lids.markup_cost) as markup_cost,
        max(lids.currency_code) as currency_code,
        max(lids.shared_projects) as shared_projects,
        max(lids.source_uuid::text)::uuid as source_uuid,
        lids.tags_hash,
        lids.namespace_hash
    FROM (
        SELECT 'AWS'::text AS source_type,
            aws.cluster_id,
            aws.cluster_alias,
            aws.namespace,
            aws.node,
            aws.resource_id,
            aws.usage_start,
            aws.usage_end,
            aws.usage_account_id,
            aws.account_alias_id,
            aws.product_code,
            aws.product_family,
            aws.instance_type,
            aws.region,
            aws.availability_zone,
            aws.tags,
            aws.usage_amount,
            aws.unit,
            aws.unblended_cost,
            aws.markup_cost,
            aws.currency_code,
            aws.shared_projects,
            aws.source_uuid,
            public.jsonb_sha256_text(aws.tags) as tags_hash,
            encode(sha256(decode(array_to_string(aws.namespace, '|'), 'escape')), 'hex') as namespace_hash
        FROM reporting_ocpawscostlineitem_daily_summary AS aws
        WHERE aws.usage_start >= date_trunc('month'::text, (now() - '2 month'::interval))::date

        UNION

        SELECT 'Azure'::text AS source_type,
            azure.cluster_id,
            azure.cluster_alias,
            azure.namespace,
            azure.node,
            azure.resource_id,
            azure.usage_start,
            azure.usage_end,
            azure.subscription_guid AS usage_account_id,
            NULL::integer AS account_alias_id,
            azure.service_name AS product_code,
            NULL::character varying AS product_family,
            azure.instance_type,
            azure.resource_location AS region,
            NULL::character varying AS availability_zone,
            azure.tags,
            azure.usage_quantity AS usage_amount,
            azure.unit_of_measure AS unit,
            azure.pretax_cost AS unblended_cost,
            azure.markup_cost,
            azure.currency AS currency_code,
            azure.shared_projects,
            azure.source_uuid,
            public.jsonb_sha256_text(azure.tags) as tags_hash,
            encode(sha256(decode(array_to_string(azure.namespace, '|'), 'escape')), 'hex') as namespace_hash
        FROM reporting_ocpazurecostlineitem_daily_summary AS azure
        WHERE azure.usage_start >= date_trunc('month'::text, (now() - '2 month'::interval))::date
    ) AS lids
    GROUP BY lids.source_type,
        lids.cluster_id,
        lids.cluster_alias,
        lids.namespace,
        lids.namespace_hash,
        lids.node,
        lids.resource_id,
        lids.usage_start,
        lids.usage_account_id,
        lids.account_alias_id,
        lids.product_code,
        lids.product_family,
        lids.instance_type,
        lids.region,
        lids.availability_zone,
        lids.tags,
        lids.tags_hash
)
WITH DATA
;

/* Once sql and/or data are fixed, add WITH DATA back in */

CREATE UNIQUE INDEX ocpall_cost_daily_summary ON reporting_ocpallcostlineitem_daily_summary (
   source_type, cluster_id, namespace_hash, node, resource_id, usage_start, usage_account_id, product_code,
   product_family, instance_type, region, availability_zone, tags_hash
);

CREATE INDEX ocpall_product_code_ilike ON reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_code)::text) gin_trgm_ops);
CREATE INDEX ocpall_product_family_ilike ON reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_family)::text) gin_trgm_ops);
CREATE INDEX ocpallcstdlysumm_node ON reporting_ocpallcostlineitem_daily_summary USING btree (node text_pattern_ops);
CREATE INDEX ocpallcstdlysumm_node_like ON reporting_ocpallcostlineitem_daily_summary USING gin (node gin_trgm_ops);
CREATE INDEX ocpallcstdlysumm_nsp ON reporting_ocpallcostlineitem_daily_summary USING gin (namespace);
