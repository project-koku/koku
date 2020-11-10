INSERT INTO {{schema | sqlsafe}}.reporting_awsenabledtagkeys (key)
    SELECT DISTINCT(key)
    FROM reporting_awscostentrylineitem_daily_summary as lids,
        jsonb_each_text(lids.tags) labels
    WHERE lids.usage_start >= date({{start_date}})
        AND lids.usage_start <= date({{end_date}})
        {% if bill_ids %}
        AND lids.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
        )
        {% endif %}
        AND NOT EXISTS (
            SELECT key
            FROM {{schema | sqlsafe}}.reporting_awsenabledtagkeys
            WHERE key = labels.key
        )
        AND NOT key = ANY(SELECT DISTINCT(key) FROM {{schema | sqlsafe}}.reporting_awstags_summary)
;
