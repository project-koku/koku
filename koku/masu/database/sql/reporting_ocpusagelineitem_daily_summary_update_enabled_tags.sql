WITH cte_array_agg_keys AS (
    SELECT array_agg(key) as key_array
    FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys
),
cte_filtered_pod_labels AS (
    SELECT uuid,
        jsonb_object_agg(key,value) as pod_labels
    FROM (
        SELECT lids.uuid,
            lids.pod_labels as ocp_tags,
            aak.key_array
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
        JOIN cte_array_agg_keys aak
            ON 1=1
        WHERE lids.pod_labels ?| aak.key_array
            AND lids.usage_start >= date({{start_date}})
            AND lids.usage_start <= date({{end_date}})
            {% if bill_ids %}
            AND lids.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids  -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%})
            {% endif %}
    ) AS lids,
    jsonb_each_text(lids.ocp_tags) AS labels
    WHERE key = ANY (key_array)
    GROUP BY lids.uuid
),
cte_filtered_volume_labels AS (
    SELECT uuid,
        jsonb_object_agg(key,value) as volume_labels
    FROM (
        SELECT lids.uuid,
            lids.volume_labels as ocp_tags,
            aak.key_array
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
        JOIN cte_array_agg_keys aak
            ON 1=1
        WHERE lids.volume_labels ?| aak.key_array
            AND lids.usage_start >= date({{start_date}})
            AND lids.usage_start <= date({{end_date}})
            {% if bill_ids %}
            AND lids.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids  -%}
                    {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%})
            {% endif %}
    ) AS lids,
    jsonb_each_text(lids.ocp_tags) AS labels
    WHERE key = ANY (key_array)
    GROUP BY lids.uuid
),
cte_joined_tags AS (
    SELECT f.uuid,
        CASE WHEN f.pod_labels IS NOT NULL
            THEN f.pod_labels
            ELSE '{}'::jsonb
            END AS pod_labels,
        CASE WHEN f.volume_labels IS NOT NULL
            THEN f.volume_labels
            ELSE '{}'::jsonb
            END AS volume_labels
    FROM (
        SELECT lids.uuid,
            fpl.pod_labels,
            fvl.volume_labels
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
        LEFT JOIN cte_filtered_pod_labels AS fpl
            ON lids.uuid = fpl.uuid
        LEFT JOIN cte_filtered_volume_labels AS fvl
            ON lids.uuid = fvl.uuid
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
UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    SET pod_labels = jt.pod_labels,
        volume_labels = jt.volume_labels
FROM cte_joined_tags AS jt
WHERE lids.uuid = jt.uuid
