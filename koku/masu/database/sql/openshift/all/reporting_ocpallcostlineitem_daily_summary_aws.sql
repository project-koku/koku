-- OCP ON ALL DAILY SUMMARY PROCESSING (AWS DATA)

DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_daily_summary_p
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = 'AWS';


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
SELECT 'AWS'::text AS source_type,
       aws.cluster_id,
       {{cluster_alias}},
       aws.namespace,
       aws.node,
       aws.resource_id,
       aws.usage_start,
       aws.usage_end,
       max(aws.usage_account_id),
       aws.account_alias_id,
       aws.product_code,
       aws.product_family,
       aws.instance_type,
       aws.region,
       aws.availability_zone,
       aws.tags,
       sum(aws.usage_amount),
       max(aws.unit),
       sum(aws.unblended_cost),
       sum(aws.markup_cost),
       max(aws.currency_code),
       max(aws.shared_projects),
       {{source_uuid}}::uuid as source_uuid
  FROM {{schema_name | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary AS aws
 WHERE aws.usage_start >= {{start_date}}::date
   AND aws.usage_start <= {{end_date}}::date
   AND aws.cluster_id = {{cluster_id}}
   AND aws.source_uuid = {{source_uuid}}::uuid
 GROUP
    BY aws.cluster_id,
       aws.namespace,
       aws.node,
       aws.resource_id,
       aws.usage_start,
       aws.usage_end,
       aws.account_alias_id,
       aws.product_code,
       aws.product_family,
       aws.instance_type,
       aws.region,
       aws.availability_zone,
       aws.tags;
