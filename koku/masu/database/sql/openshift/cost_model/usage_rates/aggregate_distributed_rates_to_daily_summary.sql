-- Copy one distribution type's rates_to_usage rows into the daily summary for a window (COST-8586).
--
-- A full-month distribution (GPU unallocated) runs over a whole month, which can differ from
-- the run's window: the whole month for a past-month run, the previous month on the 2nd of
-- the month. The distribution deleted that window's daily summary rows of its
-- cost_model_rate_type and wrote new ones to rates_to_usage; aggregate_rates_to_daily_summary
-- only covers the run's window. This step covers the distribution's window.
--
-- It replaces only rows of the given type, so running it after the main aggregate (which
-- also inserted this type's rows for the run's window) leaves one copy of each row.
-- The INSERT matches Step 3 of aggregate_rates_to_daily_summary.sql.
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}}
  AND cost_model_rate_type = {{cost_model_rate_type}};

INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid, report_period_id, cluster_id, cluster_alias, namespace, node,
    usage_start, usage_end, data_source, source_uuid,
    persistentvolumeclaim,
    pod_labels, volume_labels, all_labels,
    cost_category_id, cost_model_rate_type,
    cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
    cost_model_gpu_cost,
    distributed_cost,
    monthly_cost_type,
    raw_currency
)
SELECT
    uuid_generate_v4(),
    rtu.report_period_id,
    rtu.cluster_id,
    rtu.cluster_alias,
    rtu.namespace,
    rtu.node,
    rtu.usage_start,
    rtu.usage_start + interval '1 day' AS usage_end,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    MIN(rtu.pod_labels::text)::jsonb AS pod_labels,
    MIN(rtu.volume_labels::text)::jsonb AS volume_labels,
    MIN(rtu.all_labels::text)::jsonb AS all_labels,
    rtu.cost_category_id,
    rtu.cost_model_rate_type,
    SUM(CASE WHEN rtu.metric_type = 'cpu'     THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'memory'  THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'storage' THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'gpu'     THEN rtu.calculated_cost ELSE 0 END),
    SUM(COALESCE(rtu.distributed_cost, 0)),
    rtu.monthly_cost_type,
    CASE WHEN rtu.monthly_cost_type IN ('unattributed_network', 'unattributed_storage')
         THEN {{cost_model_currency}}
         ELSE NULL
    END
FROM {{schema | sqlsafe}}.rates_to_usage rtu
WHERE rtu.usage_start >= {{start_date}}
  AND rtu.usage_start <= {{end_date}}
  AND rtu.source_uuid = {{source_uuid}}
  AND rtu.report_period_id = {{report_period_id}}
  AND rtu.monthly_cost_type = {{cost_model_rate_type}}
GROUP BY
    rtu.report_period_id,
    rtu.cluster_id,
    rtu.cluster_alias,
    rtu.namespace,
    rtu.node,
    rtu.usage_start,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    rtu.label_hash,
    rtu.cost_category_id,
    rtu.cost_model_rate_type,
    rtu.monthly_cost_type;
