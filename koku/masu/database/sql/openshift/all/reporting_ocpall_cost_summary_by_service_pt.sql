-- OCP ON ALL COST SUMMARY BY ACCOUNT PROCESSING
-- CLEAR DATA FROM reporting_ocpall_cost_summary_by_service_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpall_cost_summary_by_service_pt
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}}
;


-- INSERT NEW DATA INTO reporting_ocpall_cost_summary_by_service_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
INSERT
  INTO {{schema_name | sqlsafe}}.reporting_ocpall_cost_summary_by_service_pt (
           source_type,
           usage_start,
           usage_end,
           cluster_id,
           cluster_alias,
           usage_account_id,
           account_alias_id,
           product_code,
           product_family,
           unblended_cost,
           markup_cost,
           currency_code,
           cost_category_id,
           source_uuid
       )
SELECT {{source_type}},
       usage_start as usage_start,
       usage_start as usage_end,
       {{cluster_id}},
       {{cluster_alias}},
       usage_account_id,
       max(account_alias_id) as account_alias_id,
       product_code,
       product_family,
       sum(unblended_cost) as unblended_cost,
       sum(markup_cost) as markup_cost,
       max(currency_code) as currency_code,
       max(cost_category_id) as cost_category_id,
       {{source_uuid}}::uuid
  FROM {{schema_name | sqlsafe}}.reporting_ocpallcostlineitem_daily_summary_p
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}}
 GROUP
    BY usage_start,
       usage_account_id,
       product_code,
       product_family
;
