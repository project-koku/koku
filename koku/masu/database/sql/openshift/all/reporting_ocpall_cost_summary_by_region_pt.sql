-- OCP ON ALL COST SUMMARY BY REGION PROCESSING
-- CLEAR DATA FROM reporting_ocpall_cost_summary_by_region_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpall_cost_summary_by_region_pt
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}}
;

-- INSERT NEW DATA INTO reporting_ocpall_cost_summary_by_region_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
INSERT
  INTO {{schema_name | sqlsafe}}.reporting_ocpall_cost_summary_by_region_pt (
           source_type,
           usage_start,
           usage_end,
           cluster_id,
           cluster_alias,
           usage_account_id,
           account_alias_id,
           region,
           availability_zone,
           unblended_cost,
           markup_cost,
           currency_code,
           source_uuid
       )
SELECT {{source_type}},
       usage_start,
       usage_start,
       {{cluster_id}},
       {{cluster_alias}},
       usage_account_id,
       max(account_alias_id),
       region,
       availability_zone,
       sum(unblended_cost),
       sum(markup_cost),
       max(currency_code),
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
       region,
       availability_zone
;
