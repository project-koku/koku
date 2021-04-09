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
    lids.project_costs as project_costs,
    max(lids.source_uuid::text)::uuid as source_uuid
   FROM ( SELECT 'AWS'::text AS source_type,
            reporting_ocpawscostlineitem_daily_summary.cluster_id,
            reporting_ocpawscostlineitem_daily_summary.cluster_alias,
            reporting_ocpawscostlineitem_daily_summary.namespace,
            (reporting_ocpawscostlineitem_daily_summary.node)::text AS node,
            reporting_ocpawscostlineitem_daily_summary.resource_id,
            reporting_ocpawscostlineitem_daily_summary.usage_start,
            reporting_ocpawscostlineitem_daily_summary.usage_end,
            reporting_ocpawscostlineitem_daily_summary.usage_account_id,
            reporting_ocpawscostlineitem_daily_summary.account_alias_id,
            reporting_ocpawscostlineitem_daily_summary.product_code,
            reporting_ocpawscostlineitem_daily_summary.product_family,
            reporting_ocpawscostlineitem_daily_summary.instance_type,
            reporting_ocpawscostlineitem_daily_summary.region,
            reporting_ocpawscostlineitem_daily_summary.availability_zone,
            reporting_ocpawscostlineitem_daily_summary.tags,
            reporting_ocpawscostlineitem_daily_summary.usage_amount,
            reporting_ocpawscostlineitem_daily_summary.unit,
            reporting_ocpawscostlineitem_daily_summary.unblended_cost,
            reporting_ocpawscostlineitem_daily_summary.markup_cost,
            reporting_ocpawscostlineitem_daily_summary.currency_code,
            reporting_ocpawscostlineitem_daily_summary.shared_projects,
            reporting_ocpawscostlineitem_daily_summary.project_costs,
            reporting_ocpawscostlineitem_daily_summary.source_uuid
           FROM reporting_ocpawscostlineitem_daily_summary
          WHERE reporting_ocpawscostlineitem_daily_summary.usage_start
                    >= date_trunc('month'::text, (now() - '1 mon'::interval))::date
        UNION
         SELECT 'Azure'::text AS source_type,
            reporting_ocpazurecostlineitem_daily_summary.cluster_id,
            reporting_ocpazurecostlineitem_daily_summary.cluster_alias,
            reporting_ocpazurecostlineitem_daily_summary.namespace,
            (reporting_ocpazurecostlineitem_daily_summary.node)::text AS node,
            reporting_ocpazurecostlineitem_daily_summary.resource_id,
            reporting_ocpazurecostlineitem_daily_summary.usage_start,
            reporting_ocpazurecostlineitem_daily_summary.usage_end,
            reporting_ocpazurecostlineitem_daily_summary.subscription_guid AS usage_account_id,
            NULL::integer AS account_alias_id,
            reporting_ocpazurecostlineitem_daily_summary.service_name AS product_code,
            NULL::character varying AS product_family,
            reporting_ocpazurecostlineitem_daily_summary.instance_type,
            reporting_ocpazurecostlineitem_daily_summary.resource_location AS region,
            NULL::character varying AS availability_zone,
            reporting_ocpazurecostlineitem_daily_summary.tags,
            reporting_ocpazurecostlineitem_daily_summary.usage_quantity AS usage_amount,
            reporting_ocpazurecostlineitem_daily_summary.unit_of_measure AS unit,
            reporting_ocpazurecostlineitem_daily_summary.pretax_cost AS unblended_cost,
            reporting_ocpazurecostlineitem_daily_summary.markup_cost,
            reporting_ocpazurecostlineitem_daily_summary.currency AS currency_code,
            reporting_ocpazurecostlineitem_daily_summary.shared_projects,
            reporting_ocpazurecostlineitem_daily_summary.project_costs,
            reporting_ocpazurecostlineitem_daily_summary.source_uuid
           FROM reporting_ocpazurecostlineitem_daily_summary
          WHERE reporting_ocpazurecostlineitem_daily_summary.usage_start
                    >= date_trunc('month'::text, (now() - '1 mon'::interval))::date) lids
 GROUP BY source_type, usage_start, cluster_id, namespace, node, usage_account_id, resource_id,
          product_code, product_family, instance_type, region, availability_zone, tags, project_costs
)
WITH DATA
;


CREATE UNIQUE INDEX ocpall_cost_daily_summary ON reporting_ocpallcostlineitem_daily_summary USING btree
                    (source_type, usage_start, cluster_id, namespace, node, usage_account_id, resource_id,
                     product_code, product_family, instance_type, region, availability_zone, tags);

CREATE INDEX ocpall_product_code_ilike ON reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_code)::text) gin_trgm_ops);
CREATE INDEX ocpall_product_family_ilike ON reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_family)::text) gin_trgm_ops);
CREATE INDEX ocpallcstdlysumm_node ON reporting_ocpallcostlineitem_daily_summary USING btree (node text_pattern_ops);
CREATE INDEX ocpallcstdlysumm_node_like ON reporting_ocpallcostlineitem_daily_summary USING gin (node gin_trgm_ops);
CREATE INDEX ocpallcstdlysumm_nsp ON reporting_ocpallcostlineitem_daily_summary USING gin (namespace);
