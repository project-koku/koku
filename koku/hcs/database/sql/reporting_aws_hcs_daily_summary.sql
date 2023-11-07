SELECT
  *,
  {{ebs_acct_num}} as ebs_account_id,
  {{org_id}} as org_id
FROM
  hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
  source = {{provider_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  AND (
    (
      bill_billingentity = 'AWS Marketplace'
      AND lineitem_legalentity like '%Red Hat%'
    )
    -- OR (
    --   lineitem_legalentity like '%Amazon Web Services%'
    --   AND lineitem_lineitemdescription like '%Red Hat%'
    -- )
    -- OR (
    --   lineitem_legalentity like '%Amazon Web Services%'
    --   AND lineitem_lineitemdescription like '%RHEL%'
    -- )
    -- OR (
    --   lineitem_legalentity like '%AWS%'
    --   AND lineitem_lineitemdescription like '%Red Hat%'
    -- )
    -- OR (
    --   lineitem_legalentity like '%AWS%'
    --   AND lineitem_lineitemdescription like '%RHEL%'
    -- )
  )
  AND lineitem_usagestartdate >= {{date}}
  AND lineitem_usagestartdate < date_add(
    'day', 1, {{date}}
  )
