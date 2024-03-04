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
        AND enabledtagkeys.provider_type = 'OCI'
),
cte_update_tag_keys as (
    SELECT
        lids.uuid as uuid,
        CASE
            WHEN EXISTS(
                SELECT 1 FROM cte_tag_key_mapping
                WHERE lids.tags ? child_key
                AND lids.tags ? parent_key)
            THEN
                (
                    SELECT jsonb_object_agg(
                        COALESCE(NULLIF(tag_map->>key, ''), key),
                        lids.tags->key
                    )
                    FROM jsonb_object_keys(lids.tags) AS key
                    WHERE key NOT IN (SELECT child_key FROM cte_tag_key_mapping)
                )
            ELSE
                (
                    SELECT jsonb_object_agg(
                        COALESCE(tag_map->>key, key),
                        lids.tags->key
                    )
                    FROM jsonb_object_keys(lids.tags) AS key
                )
        END as update_tags
    FROM
        {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary AS lids
    CROSS JOIN (
        SELECT
            jsonb_object_agg(child_key, parent_key) AS tag_map
        FROM cte_tag_key_mapping
    ) AS mapping
    WHERE
        lids.usage_start >= DATE({{start_date}})
        AND lids.usage_start <= DATE({{end_date}})
        AND lids.tags ?| ARRAY(SELECT child_key FROM cte_tag_key_mapping)
        {% if bill_ids %}
        AND lids.cost_entry_bill_id in {{ bill_ids | inclause }}
        {% endif %}
)
UPDATE {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary AS lids
SET tags = update_data.update_tags
FROM cte_update_tag_keys as update_data
WHERE lids.uuid = update_data.uuid
AND lids.usage_start >= DATE({{start_date}})
AND lids.usage_start <= DATE({{end_date}});
