-- Data with no estimated cost
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
  lineitem_unblendedcost,
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
  source = {{provider_uuid}}
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
  )
  AND lineitem_usagestartdate >= {{date}}
  AND lineitem_usagestartdate < date_add('day', 1, {{date}})
UNION
  -- CCSP data with an estimated cost
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
    WHEN try_cast(product_vcpu AS INT) <= 4 THEN 0.06 * lineitem_usageamount
    WHEN try_cast(product_vcpu AS INT) > 4 THEN 0.13 * lineitem_usageamount
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
  source = {{provider_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  AND (
    (
      lineitem_legalentity LIKE '%Amazon Web Services%'
      AND lineitem_lineitemdescription LIKE '%Red Hat%'
    )
    OR (
      lineitem_legalentity LIKE '%Amazon Web Services%'
      AND lineitem_lineitemdescription LIKE '%RHEL%'
    )
    OR (
      lineitem_legalentity LIKE '%AWS%'
      AND lineitem_lineitemdescription LIKE '%Red Hat%'
    )
    OR (
      lineitem_legalentity LIKE '%AWS%'
      AND lineitem_lineitemdescription LIKE '%RHEL%'
    )
  )
  AND lineitem_usagestartdate >= {{date}}
  AND lineitem_usagestartdate < date_add('day', 1, {{date}})
