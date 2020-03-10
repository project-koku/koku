DROP MATERIALIZED VIEW IF EXISTS reporting_ocpallcostlineitem_daily_summary;

CREATE OR REPLACE MATERIALIZED VIEW reporting_ocpallcostlineitem_daily_summary AS
 SELECT row_number() OVER () AS id,
    lids.source_type,
    lids.cluster_id,
    lids.cluster_alias,
    lids.namespace::text[],
    lids.node,
    lids.resource_id,
    lids.usage_start,
    lids.usage_end,
    lids.usage_account_id,
    lids.account_alias_id,
    lids.product_code,
    lids.product_family,
    lids.instance_type,
    lids.region,
    lids.availability_zone,
    lids.tags,
    lids.usage_amount,
    lids.unit,
    lids.unblended_cost,
    lids.markup_cost,
    lids.currency_code,
    lids.shared_projects,
    lids.project_costs
   FROM ( SELECT 'AWS'::text AS source_type,
            reporting_ocpawscostlineitem_daily_summary.cluster_id,
            reporting_ocpawscostlineitem_daily_summary.cluster_alias,
            reporting_ocpawscostlineitem_daily_summary.namespace::text[],
            reporting_ocpawscostlineitem_daily_summary.node::text AS node,
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
            reporting_ocpawscostlineitem_daily_summary.project_costs
           FROM reporting_ocpawscostlineitem_daily_summary
          WHERE reporting_ocpawscostlineitem_daily_summary.usage_start >= date_trunc('month'::text, now() - '1 mon'::interval)::date
        UNION
         SELECT 'Azure'::text AS source_type,
            reporting_ocpazurecostlineitem_daily_summary.cluster_id,
            reporting_ocpazurecostlineitem_daily_summary.cluster_alias,
            reporting_ocpazurecostlineitem_daily_summary.namespace::text[],
            reporting_ocpazurecostlineitem_daily_summary.node::text AS node,
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
            reporting_ocpazurecostlineitem_daily_summary.project_costs
           FROM reporting_ocpazurecostlineitem_daily_summary
          WHERE reporting_ocpazurecostlineitem_daily_summary.usage_start >= date_trunc('month'::text, now() - '1 mon'::interval)::date) lids;

CREATE INDEX ocpallcstdlysumm_node ON reporting_ocpallcostlineitem_daily_summary (node text_pattern_ops);
CREATE INDEX ocpallcstdlysumm_node_like ON reporting_ocpallcostlineitem_daily_summary USING GIN (node gin_trgm_ops);
CREATE INDEX ocpallcstdlysumm_nsp ON reporting_ocpallcostlineitem_daily_summary USING GIN (namespace);
CREATE INDEX ocpallcstdlysumm_usage_start on reporting_ocpallcostlineitem_daily_summary (usage_start); -- new!



DROP MATERIALIZED VIEW IF EXISTS reporting_ocpallcostlineitem_project_daily_summary;

CREATE OR RELPACE MATERIALIZED VIEW reporting_ocpallcostlineitem_project_daily_summary AS
 SELECT row_number() OVER () AS id,
    lids.source_type,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    lids.namespace,
    lids.node,
    lids.pod_labels,
    lids.resource_id,
    lids.usage_start,
    lids.usage_end,
    lids.usage_account_id,
    lids.account_alias_id,
    lids.product_code,
    lids.product_family,
    lids.instance_type,
    lids.region,
    lids.availability_zone,
    lids.usage_amount,
    lids.unit,
    lids.unblended_cost,
    lids.project_markup_cost,
    lids.pod_cost,
    lids.currency_code
   FROM ( SELECT 'AWS'::text AS source_type,
            reporting_ocpawscostlineitem_project_daily_summary.cluster_id,
            reporting_ocpawscostlineitem_project_daily_summary.cluster_alias,
            reporting_ocpawscostlineitem_project_daily_summary.data_source,
            reporting_ocpawscostlineitem_project_daily_summary.namespace::text AS namespace,
            reporting_ocpawscostlineitem_project_daily_summary.node::text AS node,
            reporting_ocpawscostlineitem_project_daily_summary.pod_labels,
            reporting_ocpawscostlineitem_project_daily_summary.resource_id,
            reporting_ocpawscostlineitem_project_daily_summary.usage_start,
            reporting_ocpawscostlineitem_project_daily_summary.usage_end,
            reporting_ocpawscostlineitem_project_daily_summary.usage_account_id,
            reporting_ocpawscostlineitem_project_daily_summary.account_alias_id,
            reporting_ocpawscostlineitem_project_daily_summary.product_code,
            reporting_ocpawscostlineitem_project_daily_summary.product_family,
            reporting_ocpawscostlineitem_project_daily_summary.instance_type,
            reporting_ocpawscostlineitem_project_daily_summary.region,
            reporting_ocpawscostlineitem_project_daily_summary.availability_zone,
            reporting_ocpawscostlineitem_project_daily_summary.usage_amount,
            reporting_ocpawscostlineitem_project_daily_summary.unit,
            reporting_ocpawscostlineitem_project_daily_summary.unblended_cost,
            reporting_ocpawscostlineitem_project_daily_summary.project_markup_cost,
            reporting_ocpawscostlineitem_project_daily_summary.pod_cost,
            reporting_ocpawscostlineitem_project_daily_summary.currency_code
           FROM reporting_ocpawscostlineitem_project_daily_summary
          WHERE reporting_ocpawscostlineitem_project_daily_summary.usage_start >= date_trunc('month'::text, now() - '1 mon'::interval)::date
        UNION
         SELECT 'Azure'::text AS source_type,
            reporting_ocpazurecostlineitem_project_daily_summary.cluster_id,
            reporting_ocpazurecostlineitem_project_daily_summary.cluster_alias,
            reporting_ocpazurecostlineitem_project_daily_summary.data_source,
            reporting_ocpazurecostlineitem_project_daily_summary.namespace::text AS namespace,
            reporting_ocpazurecostlineitem_project_daily_summary.node::text AS node,
            reporting_ocpazurecostlineitem_project_daily_summary.pod_labels,
            reporting_ocpazurecostlineitem_project_daily_summary.resource_id,
            reporting_ocpazurecostlineitem_project_daily_summary.usage_start,
            reporting_ocpazurecostlineitem_project_daily_summary.usage_end,
            reporting_ocpazurecostlineitem_project_daily_summary.subscription_guid AS usage_account_id,
            NULL::integer AS account_alias_id,
            reporting_ocpazurecostlineitem_project_daily_summary.service_name AS product_code,
            NULL::character varying AS product_family,
            reporting_ocpazurecostlineitem_project_daily_summary.instance_type,
            reporting_ocpazurecostlineitem_project_daily_summary.resource_location AS region,
            NULL::character varying AS availability_zone,
            reporting_ocpazurecostlineitem_project_daily_summary.usage_quantity AS usage_amount,
            reporting_ocpazurecostlineitem_project_daily_summary.unit_of_measure AS unit,
            reporting_ocpazurecostlineitem_project_daily_summary.pretax_cost AS unblended_cost,
            reporting_ocpazurecostlineitem_project_daily_summary.project_markup_cost,
            reporting_ocpazurecostlineitem_project_daily_summary.pod_cost,
            reporting_ocpazurecostlineitem_project_daily_summary.currency AS currency_code
           FROM reporting_ocpazurecostlineitem_project_daily_summary
          WHERE reporting_ocpazurecostlineitem_project_daily_summary.usage_start >= date_trunc('month'::text, now() - '1 mon'::interval)::date) lids;

CREATE INDEX ocpallcstprjdlysumm_node ON reporting_ocpallcostlineitem_project_daily_summary (node text_pattern_ops);
CREATE INDEX ocpallcstprjdlysumm_node_like ON reporting_ocpallcostlineitem_project_daily_summary USING GIN (node gin_trgm_ops);
CREATE INDEX ocpallcstprjdlysumm_nsp ON reporting_ocpallcostlineitem_project_daily_summary (namespace text_pattern_ops);
CREATE INDEX ocpallcstprjdlysumm_nsp_like ON reporting_ocpallcostlineitem_project_daily_summary USING GIN (namespace gin_trgm_ops);
CREATE INDEX ocpallcstprjdlysumm_usage_start ON reporting_ocpallcostlineitem_project_daily_summary (usage_start);  -- new
