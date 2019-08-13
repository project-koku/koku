INSERT INTO {schema}.reporting_ocpstoragevolumeclaimlabel_summary
SELECT l.key,
    array_agg(DISTINCT l.value) as values
FROM (
    SELECT key,
        value
    FROM {schema}.reporting_ocpstoragelineitem_daily AS li,
        jsonb_each_text(li.persistentvolumeclaim_labels) labels
) l
GROUP BY l.key
ON CONFLICT (key) DO UPDATE
SET values = EXCLUDED.values
;
