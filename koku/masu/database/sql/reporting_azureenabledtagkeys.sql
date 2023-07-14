INSERT INTO {{schema | sqlsafe}}.reporting_azureenabledtagkeys (key)
SELECT DISTINCT(key)
  FROM reporting_azurecostentrylineitem_daily_summary as lids,
       jsonb_each_text(lids.tags) labels
 WHERE lids.usage_start >= date({{start_date}})
   AND lids.usage_start <= date({{end_date}})
   {% if bill_ids %}
      AND lids.cost_entry_bill_id IN {{ bill_ids | inclause }}
   {% endif %}
   AND NOT EXISTS (
         SELECT key
           FROM {{schema | sqlsafe}}.reporting_azureenabledtagkeys
          WHERE key = labels.key
            AND enabled = true
       )
    AND NOT key = ANY(
          SELECT DISTINCT(key)
            FROM {{schema | sqlsafe}}.reporting_azuretags_summary
        )
ON CONFLICT (key) DO NOTHING;
