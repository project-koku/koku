-- update gcp tags leaving only enabled keys
with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
      where enabled = false
      and provider_type = 'GCP'
)
update {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary as lids
   set tags = tags - ek.keys
  from cte_enabled_keys as ek
 where ek.keys != '{}'::text[]
   and lids.usage_start >= date({{start_date}})
   and lids.usage_start <= date({{end_date}})
{% if bill_ids %}
   and lids.cost_entry_bill_id in {{ bill_ids | inclause }}
{% endif %}
;
