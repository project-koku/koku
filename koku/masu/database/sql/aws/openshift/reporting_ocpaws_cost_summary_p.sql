DELETE FROM {{schema_name | sqlsafe}}.reporting_ocpaws_cost_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_end <= {{end_date}}::date
    AND cluster_id = {{cluster_id}}
    AND source_uuid = {{source_uuid}}::uuid
;

INSERT INTO {{schema_name | sqlsafe}}.reporting_ocpaws_cost_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    unblended_cost,
    markup_cost,
    currency_code,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        {{cluster_id}},
        {{cluster_alias}},
        sum(unblended_cost),
        sum(markup_cost),
        max(currency_code),
        {{source_uuid}}::uuid
    FROM reporting_ocpawscostlineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY usage_start
;
