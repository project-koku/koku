DELETE FROM {{schema | sqlsafe}}.reporting_events_cost_summary_by_project_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}::uuid
;

INSERT INTO {{schema | sqlsafe}}.reporting_events_cost_summary_by_project_p (
    id,
    usage_start,
    usage_end,
    tenant_id,
    project_id,
    project_name,
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
        MAX(project_name) AS project_name,
        cost_type,
        SUM(raw_cost) AS raw_cost,
        SUM(markup_cost) AS markup_cost,
        currency,
        source_uuid
    FROM {{schema | sqlsafe}}.reporting_eventscostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY usage_start, tenant_id, project_id, cost_type, currency, source_uuid
;
