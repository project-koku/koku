-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpgcp_compute_summary_p (
    id,
    account_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    usage_amount,
    unit,
    instance_type,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid_generate_v4() as id,
        account_id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        instance_type,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM {{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND invoice_month = {{invoice_month}}
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY cluster_id,
        account_id,
        cluster_alias,
        usage_start,
        usage_end,
        source_uuid,
        instance_type,
        invoice_month
;
