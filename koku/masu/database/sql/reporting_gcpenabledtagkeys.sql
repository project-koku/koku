INSERT INTO {{schema | sqlsafe}}.reporting_enabledtagkeys (uuid, key, enabled, provider_type)
SELECT uuid_generate_v4() as uuid,
    key,
    false as enabled, -- GCP tags are disabled by default
    'GCP' as provider_type
  FROM reporting_gcpcostentrylineitem_daily_summary as lids,
       jsonb_each_text(lids.tags) labels
 WHERE lids.usage_start >= date({{start_date}})
   AND lids.usage_start <= date({{end_date}})
   {% if bill_ids %}
      AND lids.cost_entry_bill_id IN {{ bill_ids | inclause }}
   {% endif %}
   AND NOT EXISTS (
         SELECT key
           FROM {{schema | sqlsafe}}.reporting_enabledtagkeys
          WHERE key = labels.key
            AND provider_type = 'GCP'
       )
   AND NOT key = ANY(
         SELECT DISTINCT(key)
           FROM {{schema | sqlsafe}}.reporting_gcptags_summary
       )
    GROUP BY key
    ON CONFLICT (key, provider_type) DO NOTHING;
