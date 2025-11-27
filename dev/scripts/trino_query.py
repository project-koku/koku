import os
import sys

from koku.reportdb_accessor import get_report_db_accessor
import pyarrow.parquet as pq


parquet_dir = sys.argv[1]

account = parquet_dir.split("/")[-4]
provider_uuid = parquet_dir.split("/")[-3]

s3_path = parquet_dir.split("parquet_data/", 1)[1]
schema = f"acct{account}"
table_name = f"{schema}.data_{account}_{provider_uuid.replace('-', '_')}"

sql = f"CREATE TABLE IF NOT EXISTS {table_name} ("

parquet_file = f"{parquet_dir}/{os.listdir(parquet_dir).pop()}"
table = pq.read_table(parquet_file)
parquet_columns = table.column_names

for idx, col in enumerate(parquet_columns):
    norm_col = col.replace("/", "_").replace(":", "_").lower()
    col_type = "varchar"
    if norm_col in [
        "lineitem_normalizationfactor",
        "lineitem_normalizedusageamount",
        "lineitem_usageamount",
        "lineitem_unblendedcost",
        "lineitem_unblendedrate",
        "lineitem_blendedcost",
        "savingsplan_savingsplaneffectivecost",
        "lineitem_blendedrate",
        "pricing_publicondemandrate",
        "pricing_publicondemandcost",
    ]:
        col_type = "double"
    if norm_col in [
        "lineitem_usagestartdate",
        "lineitem_usageenddate",
        "bill_billingperiodstartdate",
        "bill_billingperiodenddate",
    ]:
        col_type = "timestamp"
    sql += f"{norm_col} {col_type}"
    if idx < (len(parquet_columns) - 1):
        sql += ","

sql += f") WITH(external_location = 's3a://{s3_path}', format = 'PARQUET')"

with get_report_db_accessor().connect(host="localhost", port=8080, user="admin", catalog="hive", schema="default") as conn:
    with conn.cursor() as cur:
        print("Creating Schema:")
        schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {schema}"
        print(schema_create_sql)
        cur.execute(schema_create_sql)
        rows = cur.fetchall()

with get_report_db_accessor().connect(host="localhost", port=8080, user="admin", catalog="hive", schema=schema) as schema_conn:
    with schema_conn.cursor() as schema_cur:
        print("Trino table create SQL:")
        print(sql)
        schema_cur.execute(sql)
        rows = schema_cur.fetchall()
        print("\nTrino Line Item Example Query:")
        schema_cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
        rows = schema_cur.fetchall()
        for row in rows:
            print(row)

print("\nPostgres DB AWS Summary Data Query Example:")
with get_report_db_accessor().connect(host="localhost", port=8080, user="admin", catalog="postgres", schema=schema) as postgres_conn:
    with postgres_conn.cursor() as postgres_cur:
        postgres_cur.execute("SELECT * FROM reporting_awscostentrylineitem_daily_summary LIMIT 3")
        rows = postgres_cur.fetchall()
        for row in rows:
            print(row)
