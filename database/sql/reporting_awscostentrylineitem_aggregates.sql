-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_aggregates_{uuid} AS (
    SELECT -30 as time_scope_value,
        'costs'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        null::Float as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '29 days'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -30 as time_scope_value,
        'instance_type'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '29 days'
        AND p.instance_type IS NOT NULL
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -30 as time_scope_value,
        'storage'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '29 days'
        AND p.product_family LIKE '%Storage%'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION


    SELECT -10 as time_scope_value,
        'costs'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        null::Float as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '9 days'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -10 as time_scope_value,
        'instance_type'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '9 days'
        AND p.instance_type IS NOT NULL
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -10 as time_scope_value,
        'storage'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= current_date - INTERVAL '9 days'
        AND p.product_family LIKE '%Storage%'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -1 as time_scope_value,
        'costs'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        null::Float as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= date_trunc('month', current_date)::date
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -1 as time_scope_value,
        'instance_type'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= date_trunc('month', current_date)::date
        AND p.instance_type IS NOT NULL
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -1 as time_scope_value,
        'storage'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= date_trunc('month', current_date)::date
        AND p.product_family LIKE '%Storage%'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -2 as time_scope_value,
        'costs'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        null::Float as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '1 month')
        AND li.usage_start < date_trunc('month', current_date)
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -2 as time_scope_value,
        'instance_type'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '1 month')
        AND li.usage_start < date_trunc('month', current_date)
        AND p.instance_type IS NOT NULL
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -2 as time_scope_value,
        'storage'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '1 month')
        AND li.usage_start < date_trunc('month', current_date)
        AND p.product_family LIKE '%Storage%'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -3 as time_scope_value,
        'costs'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        null::Float as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '2 month')
        AND li.usage_start < (date_trunc('month', current_date) - interval '1 month')
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -3 as time_scope_value,
        'instance_type'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '2 month')
        AND li.usage_start < (date_trunc('month', current_date) - interval '1 month')
        AND p.instance_type IS NOT NULL
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

    UNION

    SELECT -3 as time_scope_value,
        'storage'::text as report_type,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.product_code,
        p.region,
        li.availability_zone,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        sum(li.unblended_cost) as unblended_cost,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily as li
    JOIN reporting_awscostentryproduct as p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '2 month')
        AND li.usage_start < (date_trunc('month', current_date) - interval '1 month')
        AND p.product_family LIKE '%Storage%'
    GROUP BY li.usage_account_id, li.product_code, p.region, li.availability_zone, li.tags

)
;

-- Clear out old entries first
DELETE FROM reporting_awscostentrylineitem_aggregates;

-- Populate the aggregate data
INSERT INTO reporting_awscostentrylineitem_aggregates (
    time_scope_value,
    report_type,
    usage_account_id,
    account_alias_id,
    product_code,
    region,
    availability_zone,
    usage_amount,
    unblended_cost,
    resource_count,
    tags
)
SELECT time_scope_value,
    report_type,
    usage_account_id,
    account_alias_id,
    product_code,
    region,
    availability_zone,
    usage_amount,
    unblended_cost,
    resource_count,
    tags
FROM reporting_awscostentrylineitem_aggregates_{uuid}
;
