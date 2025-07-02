SELECT
  lineitem_resourceid,
  lineitem_usagestartdate,
  bill_payeraccountid,
  lineitem_usageaccountid,
  lineitem_legalentity,
  lineitem_lineitemdescription,
  bill_billingentity,
  lineitem_productcode,
  lineitem_availabilityzone,
  lineitem_lineitemtype,
  product_productfamily,
  product_instancetype,
  product_region,
  pricing_unit,
  resourcetags,
  costcategory,
  lineitem_usageamount,
  lineitem_normalizationfactor,
  lineitem_normalizedusageamount,
  lineitem_currencycode,
  lineitem_unblendedrate,
  CASE
    WHEN
      (
        try_cast(product_vcpu AS INT) <= 8
        AND (lineitem_lineitemdescription LIKE '%Red Hat%' OR lineitem_lineitemdescription LIKE '%RHEL%')
      ) THEN 0.0144 * lineitem_usageamount * CAST(product_vcpu AS INT)
    WHEN
      (
        try_cast(product_vcpu AS INT) <= 127
        AND (lineitem_lineitemdescription LIKE '%Red Hat%' OR lineitem_lineitemdescription LIKE '%RHEL%')
      ) THEN 0.0108 * lineitem_usageamount * CAST(product_vcpu AS INT)
    WHEN
      (
        try_cast(product_vcpu AS INT) > 127
        AND (lineitem_lineitemdescription LIKE '%Red Hat%' OR lineitem_lineitemdescription LIKE '%RHEL%')
      ) THEN 0.0096 * lineitem_usageamount * CAST(product_vcpu AS INT)
    ELSE lineitem_unblendedcost
  END AS lineitem_unblendedcost,
  lineitem_blendedrate,
  lineitem_blendedcost,
  pricing_publicondemandcost,
  pricing_publicondemandrate,
  savingsplan_savingsplaneffectivecost,
  product_productname,
  bill_invoiceid,
  product_vcpu,
  source,
  year,
  month,
  {{ebs_acct_num}} as ebs_account_id,
  {{org_id}} as org_id
FROM
  hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
  source = {{provider_uuid | string}}
  AND year = {{year}}
  AND month = {{month}}
  AND (
    -- private offer
    (
      bill_billingentity = 'AWS Marketplace'
      AND lineitem_legalentity LIKE '%Red Hat%'
    )
    -- alternative CCSP
    OR (
      lineitem_legalentity LIKE '%Amazon Web Services%'
      AND product_productname LIKE '%Red Hat%'
    )
    OR (
      lineitem_legalentity LIKE '%AWS%'
      AND product_productname LIKE '%Red Hat%'
    )
    -- CCSP with estimated costs
    OR (
      lineitem_legalentity LIKE '%Amazon Web Services%'
      AND lineitem_lineitemdescription LIKE '%Red Hat%'
      -- do not include Reserved Instance Fee
      AND lineitem_lineitemtype <> 'RIFee'
    )
    OR (
      lineitem_legalentity LIKE '%Amazon Web Services%'
      AND lineitem_lineitemdescription LIKE '%RHEL%'
      -- do not include Reserved Instance Fee
      AND lineitem_lineitemtype <> 'RIFee'
    )
    OR (
      lineitem_legalentity LIKE '%AWS%'
      AND lineitem_lineitemdescription LIKE '%Red Hat%'
      -- do not include Reserved Instance Fee
      AND lineitem_lineitemtype <> 'RIFee'
    )
    OR (
      lineitem_legalentity LIKE '%AWS%'
      AND lineitem_lineitemdescription LIKE '%RHEL%'
      -- do not include Reserved Instance Fee
      AND lineitem_lineitemtype <> 'RIFee'
    )
  )
  AND lineitem_usagestartdate >= {{date}}
  AND lineitem_usagestartdate < date_add('day', 1, {{date}})
