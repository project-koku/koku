DELETE FROM {{schema | sqlsafe}}.reporting_events_usage_summary_by_meter_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}::uuid
;

INSERT INTO {{schema | sqlsafe}}.reporting_events_usage_summary_by_meter_p (
    id,
    usage_start,
    usage_end,
    tenant_id,
    project_id,
    service,
    meter,
    instance_type,
    usage_amount,
    unit,
    cost_type,
    raw_cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid_generate_v4() AS id,
        usage_start,
        usage_start AS usage_end,
        tenant_id,
        project_id,
        service,
        meter,
        instance_type,
        SUM(usage_amount) AS usage_amount,
        unit,
        cost_type,
        SUM(raw_cost) AS raw_cost,
        SUM(markup_cost) AS markup_cost,
        currency,
        source_uuid
    FROM {{schema | sqlsafe}}.reporting_eventscostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY usage_start, tenant_id, project_id, service, meter, instance_type, unit, cost_type, currency, source_uuid
;
