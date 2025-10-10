-- This file allows us to mimic our trino logic to
-- populate the postgresql summary tables for unit testing.

INSERT INTO {{schema | sqlsafe}}.reporting_ocpgcp_database_summary_p (
    id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    usage_amount,
    unit,
    account_id,
    service_id,
    service_alias,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        account_id,
        service_id,
        service_alias,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM {{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p
    -- Get data for this month or last month
    WHERE (service_alias LIKE '%%SQL%%'
        OR service_alias LIKE '%%Spanner%%'
        OR service_alias LIKE '%%Bigtable%%'
        OR service_alias LIKE '%%Firestore%%'
        OR service_alias LIKE '%%Firebase%%'
        OR service_alias LIKE '%%Memorystore%%'
        OR service_alias LIKE '%%MongoDB%%')
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND invoice_month = {{invoice_month}}
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        account_id,
        service_id,
        service_alias,
        source_uuid,
        invoice_month
;
