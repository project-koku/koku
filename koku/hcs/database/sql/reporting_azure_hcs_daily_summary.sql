SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id, '{{org_id | sqlsafe}}' as org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
  source = '{{provider_uuid | sqlsafe}}'
  AND year = '{{year | sqlsafe}}'
  AND month = '{{month | sqlsafe}}'
  AND coalesce(date, usagedatetime) >= TIMESTAMP '{{date | sqlsafe}}'
  AND coalesce(date, usagedatetime) < date_add(
    'day', 1, TIMESTAMP '{{date | sqlsafe}}'
  )
  AND (
    (
      -- CCSP
      publishertype = 'Azure'
      AND (
        strpos(metersubcategory, 'Red Hat') > 0
        OR strpos(serviceinfo2, 'Red Hat') > 0
      )
    )
    OR (
      publishertype = 'Marketplace'
      AND (
        strpos(publishername, 'Red Hat') > 0
        OR (
          -- Alternate CCSP
          (
            publishername = 'Microsoft'
            OR publishername = 'Azure'
          )
          AND (
            strpos(metersubcategory, 'Red Hat') > 0
            OR strpos(serviceinfo2, 'Red Hat') > 0
          )
        )
      )
    )
  )
