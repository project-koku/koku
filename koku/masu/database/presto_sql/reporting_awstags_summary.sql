-- DELETE FROM postgres.{{schema | sqlsafe}}.reporting_awstags_summary
-- WHERE cost_entry_bill_id = INTEGER '{{bill_id | sqlsafe}}'
-- ;

WITH cte_tag_map AS (
    SELECT lineitem_usageaccountid as usage_account_id,
        cast(json_parse(resourcetags) as map(varchar,varchar)) as tag_map
    FROM source_7b7f286c_029a_4404_80f0_e055fc9501ea_aws_line_items
),
cte_tag_value AS (
    SELECT t.key,
        t.value,
        li.usage_account_id
    FROM cte_tag_map AS li
    CROSS JOIN UNNEST (tag_map) as t(key, value)
    GROUP BY key, value, usage_account_id
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as vals,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_tag_value AS tv
    LEFT JOIN postgres.acct10001.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    GROUP BY key, usage_account_id, aa.id
),
cte_insert_tag_summary AS (
    INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awstags_summary (uuid, key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
    SELECT uuid() as uuid,
        va.key,
        INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
        va.usage_account_id,
        va.account_alias_id,
        va.vals as "values"
    FROM cte_values_agg AS va
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awstags_summary AS ts
        ON va.key = ts.key
            AND va.usage_account_id = ts.usage_account_id
            AND ts.cost_entry_bill_id = INTEGER '{{bill_id | sqlsafe}}'
    WHERE ts.uuid IS NULL
),
cte_update_tag_summary AS (
    UPDATE postgres.{{schema | sqlsafe}}.reporting_awstags_summary
    SET values = va.vals
    FROM cte_values_agg AS va
    JOIN postgres.{{schema | sqlsafe}}.reporting_awstags_summary AS ts
        ON va.key = ts.key
            AND va.usage_account_id = ts.usage_account_id
            AND ts.cost_entry_bill_id = INTEGER '{{bill_id | sqlsafe}}'
),
cte_insert_tag_values AS (
    INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awstags_values (uuid, key, value, usage_account_ids, account_aliases)
    SELECT uuid() as uuid,
        tv.key,
        tv.value,
        array_agg(DISTINCT tv.usage_account_id) as usage_account_ids,
        array_agg(DISTINCT aa.account_alias) as account_aliases
    FROM cte_tag_value AS tv
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    JOIN postgres.{{schema | sqlsafe}}.reporting_awstags_values AS tv
        ON va.key = tv.key
            AND va.value = tv.value
    WHERE tv.uuid IS NULL
    GROUP BY tv.key, tv.value
)
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awstags_values (uuid, key, value, usage_account_ids, account_aliases)
    SELECT uuid() as uuid,
        tv.key,
        tv.value,
        array_agg(DISTINCT tv.usage_account_id) as usage_account_ids,
        array_agg(DISTINCT aa.account_alias) as account_aliases
    FROM cte_tag_value AS tv
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    JOIN postgres.{{schema | sqlsafe}}.reporting_awstags_values AS tv
        ON va.key = tv.key
            AND va.value = tv.value
    WHERE tv.uuid IS NULL
    GROUP BY tv.key, tv.value
    ON CONFLICT (key, value) DO UPDATE SET usage_account_ids=EXCLUDED.usage_account_ids
;
;


WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id
    FROM postgres.{{schema | sqlsafe}}.reporting_awscostentrylineitem_daily AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_tag_value AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    GROUP BY key, cost_entry_bill_id, usage_account_id, aa.id
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary (uuid, key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, usage_account_id) DO UPDATE SET values=EXCLUDED.values
)
INSERT INTO {{schema | sqlsafe}}.reporting_awstags_values (uuid, key, value, usage_account_ids, account_aliases)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.usage_account_id) as usage_account_ids,
    array_agg(DISTINCT aa.account_alias) as account_aliases
FROM cte_tag_value AS tv
LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON tv.usage_account_id = aa.account_id
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET usage_account_ids=EXCLUDED.usage_account_ids
;


select map_entries()

array_join(map_values(transform_values(map_filter(map_union(labels), (k, v) -> k LIKE 'label_%'), (k, v) -> concat(k, ':', v))), '|') as pod_labels

WITH cte_tag_map AS (
    SELECT cast(json_parse(tags) as map(varchar,varchar)) as tag_map
    FROM presto_aws_daily_summary_4dba99e2_f989_4561_a0bd_f7265414bbbe
)
SELECT t.key,
    t.value
FROM cte_tag_map
CROSS JOIN UNNEST (tag_map) as t(key, value);
