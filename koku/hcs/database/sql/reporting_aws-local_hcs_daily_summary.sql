SELECT
  *,
  '{{ebs_acct_num | sqlsafe}}' as ebs_account_id,
  '{{org_id | sqlsafe}}' as org_id
FROM
  hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
  source = '{{provider_uuid | sqlsafe}}'
  AND year = '{{year | sqlsafe}}'
  AND month = '{{month | sqlsafe}}'
  AND (
    (
      bill_billingentity = 'AWS Marketplace'
      AND lineitem_legalentity like '%Red Hat%'
    )
    OR (
      lineitem_legalentity like '%Amazon Web Services%'
      AND lineitem_lineitemdescription like '%Red Hat%'
    )
  )
  AND lineitem_usagestartdate >= TIMESTAMP '{{date | sqlsafe}}'
  AND lineitem_usagestartdate < date_add(
    'day', 1, TIMESTAMP '{{date | sqlsafe}}'
  )
