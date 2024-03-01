-- Delete stale enabled keys
WITH cte_tag_mapping AS(
    SELECT distinct
        array_agg(child_id) as children_uuids,
        array_agg(parent_id) as parent_uuids
    FROM reporting_tagmapping
)
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
USING cte_tag_mapping tag_map
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS pls
    WHERE pls.key = etk.key
)
AND NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS vls
    WHERE vls.key = etk.key
)
AND etk.enabled = true
AND etk.provider_type = 'OCP'
AND NOT etk.uuid = ANY(tag_map.children_uuids || tag_map.parent_uuids);
