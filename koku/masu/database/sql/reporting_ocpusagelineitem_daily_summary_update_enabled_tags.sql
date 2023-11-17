-- update ocp tags leaving only enabled keys
with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
      where enabled = false
      and provider_type = 'OCP'
)
update {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    set pod_labels = case
        when pod_labels = '"{}"' then '{}'::jsonb
        else pod_labels - upd.keys
    end,
    volume_labels = case
        when volume_labels = '"{}"' then '{}'::jsonb
        else volume_labels - upd.keys
    end,
    all_labels = case
        when all_labels = '"{}"' then '{}'::jsonb
        else all_labels - upd.keys
    end
from (
    select uuid, ek.keys as keys
    from {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary, cte_enabled_keys as ek
        where usage_start >= date({{start_date}})
          and usage_start <= date({{end_date}})
          {% if report_period_ids %}
            and report_period_id IN {{ report_period_ids | inclause }}
          {% endif %}
          and ek.keys != '{}'::text[]
    order by uuid
    for update
) as upd
where lids.uuid = upd.uuid
