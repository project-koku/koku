WHERE
  source = {{source_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  AND lineitem_productcode = 'AmazonEC2'
  AND lineitem_lineitemtype IN (
    'Usage', 'SavingsPlanCoveredUsage'
  )
  AND product_vcpu != ''
  AND strpos(
    lower(resourcetags),
    'com_redhat_rhel'
  ) > 0
