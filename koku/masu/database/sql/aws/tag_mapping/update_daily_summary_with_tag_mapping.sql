WITH cte_tag_mapping AS (
    SELECT DISTINCT
        enabledtagkeys.key AS child_key,
        parent_tags.key AS parent_key
    FROM
        {{schema | sqlsafe}}.reporting_enabledtagkeys AS enabledtagkeys
        INNER JOIN {{schema | sqlsafe}}.reporting_tagmapping AS tag_mapping ON enabledtagkeys.uuid = tag_mapping.child_id
        INNER JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS parent_tags ON tag_mapping.parent_id = parent_tags.uuid
    WHERE
        enabledtagkeys.enabled
        AND enabledtagkeys.provider_type = 'AWS'
),
cte_filtered_line_items AS (
    SELECT
        lids.uuid AS uuid,
        lids.tags AS original_tags,
        mapping.tag_map AS tag_map,
        EXISTS (
            SELECT 1
            FROM cte_tag_mapping
            WHERE child_key IN (SELECT jsonb_object_keys(lids.tags))
            AND parent_key = any(array(SELECT jsonb_object_keys(lids.tags)::text))
        ) AS key_collision
    FROM
        {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS lids
    CROSS JOIN (
        SELECT
            jsonb_object_agg(child_key, parent_key) AS tag_map
        FROM cte_tag_mapping
    ) AS mapping
    WHERE
        lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.tags ?| ARRAY(SELECT child_key FROM cte_tag_mapping)
        {% if bill_ids %}
        AND lids.cost_entry_bill_id in {{ bill_ids | inclause }}
        {% endif %}
),
cte_update_data as (
    SELECT
        filtered_rows.uuid,
        filtered_rows.original_tags,
        CASE
            WHEN filtered_rows.key_collision = TRUE THEN
                jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        original_tags->key
                )
            ELSE
                jsonb_object_agg(
                    COALESCE(tag_map->>key, key),
                    original_tags->key
                )
        END AS updated_tags
    FROM
        {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS lids
    INNER JOIN cte_filtered_line_items AS filtered_rows ON lids.uuid = filtered_rows.uuid
    CROSS JOIN LATERAL jsonb_object_keys(lids.tags) AS key
    GROUP BY filtered_rows.uuid, filtered_rows.original_tags, filtered_rows.key_collision, filtered_rows.tag_map
)
UPDATE {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS lids
SET tags = update_data.updated_tags
FROM cte_update_data as update_data
WHERE lids.uuid = update_data.uuid;
