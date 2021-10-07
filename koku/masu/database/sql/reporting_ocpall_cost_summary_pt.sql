-- OCP ON ALL COST SUMMARY PROCESSING (AWS DATA)
-- CLEAR DATA FROM reporting_ocpall_cost_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type_upper}}; source {{source_uuid}}; cluster {{cluster_id}}
DELETE
  FROM reporting_ocpall_cost_summary_pt
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}};


-- INSERT NEW DATA INTO reporting_ocpall_cost_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type_upper}}; source {{source_uuid}}; cluster {{cluster_id}}
INSERT
  INTO reporting_ocpall_cost_summary_pt
       (
           data_source,
           usage_start,
           usage_end,
           cluster_id,
           cluster_alias,
           sum(unblended_cost),
           sum(markup_cost),
           max(currency_code),
           {{source_uuid}}
       )
SELECT {{source_type}},
       usage_start,
       usage_start,
       cluster_id,
       {{cluster_alias}},
       sum(unblended_cost),
       sum(markup_cost),
       max(currency_code),
       {{source_uuid}}
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}}
 GROUP
    BY usage_start,
       cluster_id
;
