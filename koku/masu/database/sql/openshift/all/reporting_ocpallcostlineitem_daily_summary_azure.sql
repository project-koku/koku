-- OCP ON ALL DAILY SUMMARY PROCESSING (AZURE DATA)

DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_daily_summary_p
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = 'Azure';


INSERT
  INTO {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_daily_summary_p (
           source_type,
           cluster_id,
           cluster_alias,
           namespace,
           node,
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
           source_uuid
       )
SELECT 'Azure'::text AS source_type,
       azure.cluster_id,
       {{cluster_alias}},
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
       sum(azure.usage_quantity) AS usage_amount,
       max(azure.unit_of_measure) AS unit,
       sum(azure.pretax_cost) AS unblended_cost,
       sum(azure.markup_cost),
       max(azure.currency) AS currency_code,
       max(azure.shared_projects),
       {{source_uuid}}::uuid as source_uuid
  FROM {{schema_name | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary AS azure
 WHERE azure.usage_start >= {{start_date}}::date
   AND azure.usage_start <= {{end_date}}::date
   AND azure.cluster_id = {{cluster_id}}
   AND azure.source_uuid = {{source_uuid}}::uuid
 GROUP
    BY azure.cluster_id,
       azure.namespace,
       azure.node,
       azure.resource_id,
       azure.usage_start,
       azure.usage_end,
       azure.subscription_guid,
       azure.service_name,
       azure.instance_type,
       azure.resource_location,
       azure.tags;
