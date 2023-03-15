SELECT
  *,
  '{{ebs_acct_num | sqlsafe}}' as ebs_account_id,
  '{{org_id | sqlsafe}}' as org_id
FROM
  hive.{ { schema | sqlsafe } }.{ { table | sqlsafe } }
WHERE
  source = '{{provider_uuid | sqlsafe}}'
  AND year = '{{year | sqlsafe}}'
  AND month = '{{month | sqlsafe}}'
  AND (
    regexp_like(
      bill_billingentity,
      'AWS Marketplace|Amazon Web Services Marketplace'
    )
    AND regexp_like(lineitem_legalentity, 'RHEL|Red Hat')
  )
  OR (
    regexp_like(
      lineitem_legalentity,
      'AWS|Amazon Web Services'
    )
    AND regexp_like(lineitem_lineitemdescription, 'RHEL|Red Hat')
  )
  AND lineitem_usagestartdate >= TIMESTAMP '{{date | sqlsafe}}'
  AND lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
