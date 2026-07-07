-- Delete stale monthly-cost rows from rates_to_usage before re-inserting.
--
-- populate_monthly_cost_sql() always calls _delete_monthly_cost_model_data()
-- first, but that DELETE only targets the legacy
-- reporting_ocpusagelineitem_daily_summary table. monthly_cost_cluster_and_node.sql,
-- monthly_cost_persistentvolumeclaim.sql, and monthly_cost_virtual_machine.sql are
-- pure INSERT...SELECT into rates_to_usage with no matching DELETE, so every
-- re-run of monthly-cost population (cost model rate edits, re-summarization,
-- orchestrator re-runs) duplicated Node/Cluster/PVC/OCP_VM monthly-cost rows
-- instead of replacing them. Mirrors delete_distributed_rates_to_usage.sql,
-- which fixed the identical gap for distribution rows.
--
-- No rate_type filter, matching delete_monthly_cost.sql: a rate's
-- Infrastructure/Supplementary classification can change between runs, so all
-- rows for this monthly_cost_type must be cleared regardless of their
-- previously-recorded cost_model_rate_type.
DELETE FROM {{schema | sqlsafe}}.rates_to_usage AS rtu
WHERE rtu.usage_start >= {{start_date}}::date
    AND rtu.usage_start <= {{end_date}}::date
    AND rtu.report_period_id = {{report_period_id}}
    AND rtu.monthly_cost_type = {{cost_type}}
;
