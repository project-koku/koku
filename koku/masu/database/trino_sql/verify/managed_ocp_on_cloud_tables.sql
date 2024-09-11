SELECT
    count_1 = count_2 AS counts_match
FROM
    (
        SELECT COUNT(*) AS count_1
        FROM hive.{{schema | sqlsafe}}.{{managed_table | sqlsafe}} as managed_ocpaws
        WHERE managed_ocpaws.source = {{aws_source_uuid}}
        AND managed_ocpaws.year = {{year}}
        AND managed_ocpaws.month = {{month}}
    ) t1,
    (
        SELECT COUNT(*) AS count_2
        FROM hive.{{schema | sqlsafe}}.{{parquet_table | sqlsafe}} as parquet_table
        WHERE parquet_table.source = {{aws_source_uuid}}
        AND parquet_table.year = {{year}}
        AND parquet_table.month = {{month}}
    ) t2;
