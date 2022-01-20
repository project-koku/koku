-- OCP ON ALL DAILY SUMMARY PROCESSING (GCP DATA)

DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_daily_summary_p
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = 'GCP';


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
SELECT 'GCP'::text AS source_type,
       gcp.cluster_id,
       {{cluster_alias}},
       gcp.namespace,
       gcp.node,
       gcp.resource_id,
       gcp.usage_start,
       gcp.usage_end,
       max(gcp.account_id),
       NULL::integer AS account_alias_id,
       gcp.service_alias AS product_code,
       NULL::character varying AS product_family,
       gcp.instance_type,
       gcp.region,
       NULL::character varying AS availability_zone,
       gcp.tags,
       sum(gcp.usage_amount),
       max(gcp.unit),
       sum(gcp.unblended_cost),
       sum(gcp.markup_cost),
       max(gcp.currency) AS currency_code,
       max(gcp.shared_projects),
       {{source_uuid}}::uuid as source_uuid
  FROM {{schema_name | sqlsafe}}.reporting_ocpgcpcostlineitem_daily_summary_p AS gcp
 WHERE gcp.usage_start >= {{start_date}}::date
   AND gcp.usage_start <= {{end_date}}::date
   AND gcp.cluster_id = {{cluster_id}}
   AND gcp.source_uuid = {{source_uuid}}::uuid
 GROUP
    BY gcp.cluster_id,
       gcp.namespace,
       gcp.node,
       gcp.resource_id,
       gcp.usage_start,
       gcp.usage_end,
       gcp.account_id,
       gcp.service_alias,
       gcp.instance_type,
       gcp.region,
       gcp.tags;
