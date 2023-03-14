-- update aws tags leaving only enabled keys
with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_awsenabledtagkeys
      where enabled = false
)
update {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary as lids
   set tags = tags - ek.keys
  from cte_enabled_keys as ek
 where ek.keys != '{}'::text[]
   and lids.usage_start >= date({{start_date}})
   and lids.usage_start <= date({{end_date}})
{% if bill_ids %}
   and lids.cost_entry_bill_id IN (
       {%- for bill_id in bill_ids  -%}
           {{bill_id}}{% if not loop.last %},{% endif %}
       {%- endfor -%})
{% endif %}
;
