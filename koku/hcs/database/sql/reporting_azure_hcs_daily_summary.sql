SELECT
  *,
  {{ebs_acct_num}} as ebs_account_id,
  {{org_id}} as org_id
FROM
  hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
  source = {{provider_uuid | string}}
  AND year = {{year}}
  AND month = {{month}}
  AND date >= {{date}}
  AND date < date_add(
    'day', 1, {{date}}
  )
  AND (
    (
      -- CCSP
      publishertype = 'Azure'
      AND strpos(metersubcategory, 'Red Hat') > 0
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
          AND strpos(metersubcategory, 'Red Hat') > 0
        )
      )
    )
  )
