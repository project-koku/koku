-- Delete stale enabled keys
WITH cte_tag_mapping AS(
    SELECT
        array_agg(child_id) as children_uuids,
        array_agg(distinct parent_id) as parent_uuids
    FROM reporting_tagmapping
)
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys etk
USING cte_tag_mapping tag_map
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts
    WHERE ts.key = etk.key
        AND etk.provider_type = 'Azure'
)
AND etk.enabled = true
AND etk.provider_type = 'Azure'
AND NOT etk.uuid = ANY(tag_map.children_uuids || tag_map.parent_uuids);
