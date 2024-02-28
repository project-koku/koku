-- Delete stale enabled keys
WITH cte_tag_mapping AS(
    SELECT distinct
        array_agg(child_id) as children_uuids,
        array_agg(parent_id) as parent_uuids
    FROM reporting_tagmapping
)
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_gcptags_summary AS ts
    WHERE ts.key = etk.key
        AND etk.provider_type = 'GCP'
)
AND etk.enabled = true
and etk.provider_type = 'GCP'
AND NOT etk.uuid = ANY(tag_map.children_uuids || tag_map.parent_uuids);
