WITH cte_tag_key_mapping AS (
    SELECT DISTINCT
        enabledtagkeys.key as child_key,
        parent_tags.key as parent_key
    FROM
        {{schema | sqlsafe}}.reporting_enabledtagkeys AS enabledtagkeys
        INNER JOIN {{schema | sqlsafe}}.reporting_tagmapping AS tag_mapping ON enabledtagkeys.uuid = tag_mapping.child_id
        INNER JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS parent_tags ON tag_mapping.parent_id = parent_tags.uuid
    WHERE
        enabledtagkeys.enabled
        AND enabledtagkeys.provider_type = 'OCP'
),
cte_labels_to_update as (
    SELECT
        lids.uuid as uuid,
        'pod_labels' AS label_type,
        lids.pod_labels AS labels,
        EXISTS(
            SELECT 1 FROM cte_tag_key_mapping
            WHERE lids.pod_labels ? child_key
            AND lids.pod_labels ? parent_key
        ) as parent_and_child_present
    FROM
        {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    WHERE lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.pod_labels IS NOT NULL
        AND lids.pod_labels != '{}'::jsonb
        AND lids.pod_labels ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if report_period_ids %}
            AND lids.report_period_id IN {{ report_period_ids | inclause }}
        {% endif %}
    UNION ALL
    SELECT
        lids.uuid as uuid,
        'volume_labels' AS label_type,
        lids.volume_labels AS labels,
        EXISTS(
            SELECT 1 FROM cte_tag_key_mapping
            WHERE lids.volume_labels ? child_key
            AND lids.volume_labels ? parent_key
        ) as parent_and_child_present
    FROM
        {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    WHERE lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.volume_labels IS NOT NULL
        AND lids.volume_labels != '{}'::jsonb
        AND lids.volume_labels ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if report_period_ids %}
            AND lids.report_period_id IN {{ report_period_ids | inclause }}
        {% endif %}
),
cte_update_labels as (
    SELECT
        uuid,
        label_type,
        CASE
            WHEN parent_and_child_present
            THEN
                (
                    SELECT jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        labels->key
                    )
                    FROM jsonb_object_keys(labels) AS key
                    WHERE key NOT IN (SELECT child_key FROM cte_tag_key_mapping)
                )
            ELSE
                (
                    SELECT jsonb_object_agg(
                        COALESCE(tag_map->>key, key),
                        labels->key
                    )
                    FROM jsonb_object_keys(labels) AS key
                )
        END as updated_labels
    FROM cte_labels_to_update
    CROSS JOIN (SELECT jsonb_object_agg(child_key, parent_key) AS tag_map FROM cte_tag_key_mapping) AS mapping
)
UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
SET
    pod_labels = CASE WHEN update_data.label_type = 'pod_labels' THEN update_data.updated_labels ELSE lids.pod_labels END,
    volume_labels = CASE WHEN update_data.label_type = 'volume_labels' THEN update_data.updated_labels ELSE lids.volume_labels END,
    all_labels = update_data.updated_labels
FROM cte_update_labels AS update_data
WHERE lids.uuid = update_data.uuid
AND lids.usage_start >= DATE({{start_date}})
AND lids.usage_start <= DATE({{end_date}});
