-- OCP ON ALL COMPUTE SUMMARY PROCESSING (AWS DATA)
-- CLEAR DATA FROM reporting_ocpall_compute_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type_upper}}; source {{source_uuid}}; cluster {{cluster_id}}
DELETE
  FROM reporting_ocpall_compute_summary_pt
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}};


-- INSERT NEW DATA INTO reporting_ocpall_compute_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type_upper}}; source {{source_uuid}}; cluster {{cluster_id}}
INSERT
  INTO reporting_ocpall_compute_summary_pt
       (
           data_source,
           usage_start,
           usage_end,
           cluster_id,
           cluster_alias,
           usage_account_id,
           account_alias_id,
           product_code,
           instance_type,
           resource_id,
           usage_amount,
           unit,
           unblended_cost,
           markup_cost,
           currency_code,
           source_uuid
       )
SELECT source_type,
       usage_start,
       usage_start,
       cluster_id,
       {{cluster_alias}},
       usage_account_id,
       max(account_alias_id),
       product_code,
       instance_type,
       resource_id,
       sum(usage_amount),
       max(unit),
       sum(unblended_cost),
       sum(markup_cost),
       max(currency_code),
       {{source_uuid}}
  FROM reporting_ocpallcostlineitem_daily_summary_p
 WHERE usage_start >= {{start_date}}
   AND usage_end <= {{end_date}}
   AND source_type = {{source_type}};
   AND cluster_id = {{cluster_id}}
   AND source_uuid = {{source_uuid}}::uuid
   AND instance_type IS NOT NULL
 GROUP
    BY usage_start,
       cluster_id,
       usage_account_id,
       product_code,
       instance_type,
       resource_id
;
