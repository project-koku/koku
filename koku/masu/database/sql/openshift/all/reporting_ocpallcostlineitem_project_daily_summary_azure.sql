-- OCP ON ALL PROJECT DAILY SUMMARY PROCESSING (AZURE DATA)

DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_project_daily_summary_p
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = 'Azure';


INSERT
  INTO {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_project_daily_summary_p (
           source_type,
           cluster_id,
           cluster_alias,
           data_source,
           namespace,
           node,
           pod_labels,
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
           usage_amount,
           unit,
           unblended_cost,
           project_markup_cost,
           pod_cost,
           currency_code,
           source_uuid
       )
SELECT 'Azure' as source_type,
       cluster_id,
       {{cluster_alias}} as cluster_alias,
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
       {{source_uuid}}::uuid as source_uuid
  FROM {{schema_name | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND cluster_id = {{cluster_id}}
   AND source_uuid = {{source_uuid}}::uuid
 GROUP
    BY usage_start,
       usage_end,
       cluster_id,
       data_source,
       namespace,
       node,
       usage_account_id,
       resource_id,
       product_code,
       instance_type,
       region,
       pod_labels;
