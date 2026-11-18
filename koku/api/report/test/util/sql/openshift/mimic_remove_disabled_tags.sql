-- This file allows us to mimic our trino logic to
-- remove disabled keys in postgresql for unit testing.

with cte_enabled_keys as (
    select coalesce(array_agg(key), '{}'::text[])::text[] as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
      where enabled = false
      and provider_type = 'OCP'
)
update {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    set pod_labels = case
        when pod_labels = '"{}"' then '{}'::jsonb
        else pod_labels - ek.keys
    end,
    volume_labels = case
        when volume_labels = '"{}"' then '{}'::jsonb
        else volume_labels - ek.keys
    end,
    all_labels = case
        when all_labels = '"{}"' then '{}'::jsonb
        else all_labels - ek.keys
    end

from cte_enabled_keys as ek
    where ek.keys != '{}'::text[]
        and lids.usage_start >= date({{start_date}})
        and lids.usage_start <= date({{end_date}})
        {% if report_period_ids %}
            and lids.report_period_id IN {{ report_period_ids | inclause }}
        {% endif %}
;
