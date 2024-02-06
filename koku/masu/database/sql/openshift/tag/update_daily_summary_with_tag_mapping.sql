WITH cte_tag_key_mapping AS (
    SELECT DISTINCT
        enabledtagkeys.key AS child_key,
        parent_tags.key AS parent_key
    FROM
        {{schema | sqlsafe}}.reporting_enabledtagkeys AS enabledtagkeys
        INNER JOIN {{schema | sqlsafe}}.reporting_tagmapping AS tag_mapping ON enabledtagkeys.uuid = tag_mapping.child_id
        INNER JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS parent_tags ON tag_mapping.parent_id = parent_tags.uuid
    WHERE
        enabledtagkeys.enabled
        AND enabledtagkeys.provider_type = 'OCP'
),
cte_update_pod_labels_keys as (
    SELECT
        lids.uuid as uuid,
        -- lids.pod_labels as origianl_pod_labels, --uncomment to compare
        CASE
            WHEN
                (EXISTS(SELECT 1
                FROM cte_tag_key_mapping
                WHERE child_key IN (SELECT jsonb_object_keys(lids.pod_labels))
                AND parent_key = any(array(SELECT jsonb_object_keys(lids.pod_labels)::text)))) = True
            THEN
                (
                    SELECT jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        lids.pod_labels->key
                    )
                    FROM jsonb_object_keys(lids.pod_labels) AS key
                    WHERE key NOT IN (SELECT child_key FROM cte_tag_key_mapping)
                )
            ELSE
                (
                    SELECT jsonb_object_agg(
                        COALESCE(tag_map->>key, key),
                        lids.pod_labels->key
                    )
                    FROM jsonb_object_keys(lids.pod_labels) AS key
                )
        END as update_pod_labels
    FROM
        {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    CROSS JOIN (
        SELECT
            jsonb_object_agg(child_key, parent_key) AS tag_map
        FROM cte_tag_key_mapping
    ) AS mapping
    WHERE
        lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.pod_labels ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if bill_ids %}
        AND lids.cost_entry_bill_id in {{ bill_ids | inclause }}
        {% endif %}
),
cte_update_volume_labels_keys as (
    SELECT
        lids.uuid as uuid,
        -- lids.volume_labels as origianl_volume_labels, --uncomment to compare
        CASE
            WHEN
                (EXISTS(SELECT 1
                FROM cte_tag_key_mapping
                WHERE child_key IN (SELECT jsonb_object_keys(lids.volume_labels))
                AND parent_key = any(array(SELECT jsonb_object_keys(lids.volume_labels)::text)))) = True
            THEN
                (
                    SELECT jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        lids.volume_labels->key
                    )
                    FROM jsonb_object_keys(lids.volume_labels) AS key
                    WHERE key NOT IN (SELECT child_key FROM cte_tag_key_mapping)
                )
            ELSE
                (
                    SELECT jsonb_object_agg(
                        COALESCE(tag_map->>key, key),
                        lids.volume_labels->key
                    )
                    FROM jsonb_object_keys(lids.volume_labels) AS key
                )
        END as update_volume_labels
    FROM
        {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    CROSS JOIN (
        SELECT
            jsonb_object_agg(child_key, parent_key) AS tag_map
        FROM cte_tag_key_mapping
    ) AS mapping
    WHERE
        lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.volume_labels ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if bill_ids %}
        AND lids.cost_entry_bill_id in {{ bill_ids | inclause }}
        {% endif %}
),
cte_update_all_labels_keys as (
    SELECT
        lids.uuid as uuid,
        -- lids.all_labels as origianl_all_labels, --uncomment to compare
        CASE
            WHEN
                (EXISTS(SELECT 1
                FROM cte_tag_key_mapping
                WHERE child_key IN (SELECT jsonb_object_keys(lids.all_labels))
                AND parent_key = any(array(SELECT jsonb_object_keys(lids.all_labels)::text)))) = True
            THEN
                (
                    SELECT jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        lids.all_labels->key
                    )
                    FROM jsonb_object_keys(lids.all_labels) AS key
                    WHERE key NOT IN (SELECT child_key FROM cte_tag_key_mapping)
                )
            ELSE
                (
                    SELECT jsonb_object_agg(
                        COALESCE(tag_map->>key, key),
                        lids.all_labels->key
                    )
                    FROM jsonb_object_keys(lids.all_labels) AS key
                )
        END as update_all_labels
    FROM
        {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    CROSS JOIN (
        SELECT
            jsonb_object_agg(child_key, parent_key) AS tag_map
        FROM cte_tag_key_mapping
    ) AS mapping
    WHERE
        lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.all_labels ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if bill_ids %}
        AND lids.cost_entry_bill_id in {{ bill_ids | inclause }}
        {% endif %}
)
UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
SET tags = update_data.update_tags
FROM cte_update_tag_keys as update_data
WHERE lids.uuid = update_data.uuid;
