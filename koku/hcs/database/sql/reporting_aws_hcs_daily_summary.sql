SELECT
    *,
    '{{ebs_acct_num | sqlsafe}}' AS ebs_account_id,
    '{{org_id | sqlsafe}}' AS org_id
FROM
    hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE
    source = '{{provider_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND (
        (
            bill_billingentity = 'AWS Marketplace'
            AND lineitem_legalentity LIKE '%Red Hat%'
        )
        OR (
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
    AND lineitem_usagestartdate >= TIMESTAMP '{{date | sqlsafe}}'
    AND lineitem_usagestartdate < date_add(
        'day', 1, TIMESTAMP '{{date | sqlsafe}}'
    )
;
