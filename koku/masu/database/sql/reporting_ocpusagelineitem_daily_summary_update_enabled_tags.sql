-- update ocp tags leaving only enabled keys
with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_ocpenabledtagkeys
)
update {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
   set pod_labels = pod_labels - array_subtract(array(select jsonb_object_keys(pod_labels))::text[], keys::text[]),
       volume_labels = volume_labels - array_subtract(array(select jsonb_object_keys(volume_labels))::text[], keys::text[])
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
