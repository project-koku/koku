WITH cte_array_agg_keys AS (
    SELECT array_agg(key) as key_array
    FROM {{schema | sqlsafe}}.reporting_awsenabledtagkeys
),
cte_filtered_tags AS (
    SELECT uuid,
        jsonb_object_agg(key,value) as aws_tags
    FROM (
        SELECT lids.uuid,
            lids.tags as aws_tags,
            aak.key_array
        FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary lids
        JOIN cte_array_agg_keys aak
            ON 1=1
        WHERE lids.tags ?| aak.key_array
            AND lids.usage_start >= date({{start_date}})
            AND lids.usage_start <= date({{end_date}})
            {% if bill_ids %}
            AND lids.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids  -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%})
            {% endif %}
    ) AS lids,
    jsonb_each_text(lids.aws_tags) AS labels
    WHERE key = ANY (key_array)
    GROUP BY lids.uuid
),
cte_joined_tags AS (
    SELECT f.uuid,
        CASE WHEN f.aws_tags IS NOT NULL
            THEN f.aws_tags
            ELSE '{}'::jsonb
            END AS tags
    FROM (
        SELECT lids.uuid,
            ft.aws_tags
        FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS lids
        LEFT JOIN cte_filtered_tags AS ft
            ON lids.uuid = ft.uuid
        WHERE lids.usage_start >= date({{start_date}})
            AND lids.usage_start <= date({{end_date}})
            {% if bill_ids %}
            AND lids.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids  -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%})
            {% endif %}
    ) AS f
)
UPDATE {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS lids
    SET tags = jt.tags
FROM cte_joined_tags AS jt
WHERE lids.uuid = jt.uuid
