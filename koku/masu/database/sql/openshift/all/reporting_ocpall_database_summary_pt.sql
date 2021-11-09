-- OCP ON ALL COST SUMMARY BY ACCOUNT PROCESSING
-- CLEAR DATA FROM reporting_ocpall_database_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
DELETE
  FROM {{schema_name | sqlsafe}}.reporting_ocpall_database_summary_pt
 WHERE usage_start >= {{start_date}}::date
   AND usage_start <= {{end_date}}::date
   AND source_uuid = {{source_uuid}}::uuid
   AND cluster_id = {{cluster_id}}
   AND source_type = {{source_type}}
;

-- INSERT NEW DATA INTO reporting_ocpall_database_summary_pt
-- FOR {{start_date}} - {{end_date}}; source_type {{source_type}}; source {{source_uuid}}; cluster {{cluster_id}}
INSERT
  INTO {{schema_name | sqlsafe}}.reporting_ocpall_database_summary_pt (
           source_type,
           usage_start,
           usage_end,
           cluster_id,
           cluster_alias,
           usage_account_id,
           account_alias_id,
           product_code,
           usage_amount,
           unit,
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
       product_code,
       sum(usage_amount),
       max(unit),
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
   AND (
           product_code LIKE '%%Database%%' OR
           product_code IN (
                               'AmazonRDS',
                               'AmazonDynamoDB',
                               'AmazonElastiCache',
                               'AmazonNeptune',
                               'AmazonRedshift',
                               'AmazonDocumentDB',
                               'Cosmos DB',
                               'Cache for Redis'
                           )
       )
 GROUP
    BY usage_start,
       usage_account_id,
       product_code
;
