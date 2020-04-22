UPDATE {{schema | sqlsafe}}.reporting_awsorganizationalunit
SET account_alias_id = (
    SELECT aa.id
    FROM {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    WHERE aa.account_id = {{schema | sqlsafe}}.reporting_awsorganizationalunit.account_id
);
