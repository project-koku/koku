-- update ocp tags leaving only enabled keys
with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_ocpenabledtagkeys
      where enabled = true
)
update {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
   set pod_labels = pod_labels - array_subtract(array(select jsonb_object_keys(coalesce(pod_labels, '{}'::jsonb)))::text[], keys::text[]),
       volume_labels = volume_labels - array_subtract(array(select jsonb_object_keys(coalesce(volume_labels, '{}'::jsonb)))::text[], keys::text[])
  from cte_enabled_keys as ek
 where ek.keys != '{}'::text[]
   and lids.usage_start >= date({{start_date}})
   and lids.usage_start <= date({{end_date}})
{% if report_period_ids %}
   and lids.report_period_id IN (
       {%- for rp_id in report_period_ids  -%}
           {{rp_id}}{% if not loop.last %},{% endif %}
       {%- endfor -%})
{% endif %}
;
