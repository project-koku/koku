import os
import sys

import pyarrow.parquet as pq
import trino


PRESTO_USER = os.environ.get("PRESTO_USER", "admin")
PRESTO_CATALOG = os.environ.get("PRESTO_CATALOG", "hive")
PRESTO_SCHEMA = os.environ.get("PRESTO_SCHEMA", "default")
TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
TRINO_USER = os.environ.get("TRINO_USER", "admin")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "hive")
TRINO_SCHEMA = os.environ.get("TRINO_SCHEMA", "default")

parquet_dir = sys.argv[1]

try:
    PRESTO_PORT = int(os.environ.get("PRESTO_PORT", "8080"))
except ValueError:
    PRESTO_PORT = 8080

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

conn = trino.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema="default")
cur = conn.cursor()
print("Creating Schema:")
schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {schema}"
print(schema_create_sql)
cur.execute(schema_create_sql)
rows = cur.fetchall()
conn.close()

schema_conn = trino.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema=schema)
schema_cur = conn.cursor()
print("Trino table create SQL:")
print(sql)
schema_cur.execute(sql)
rows = schema_cur.fetchall()

print("\nTrino Line Item Example Query:")
schema_cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
rows = schema_cur.fetchall()
for row in rows:
    print(row)
schema_conn.close()

print("\nPostgres DB AWS Summary Data Query Example:")
postgres_conn = trino.dbapi.connect(host="localhost", port=8080, user="admin", catalog="postgres", schema=schema)
postgres_cur = postgres_conn.cursor()

postgres_cur.execute("SELECT * FROM reporting_awscostentrylineitem_daily_summary LIMIT 3")
rows = postgres_cur.fetchall()
for row in rows:
    print(row)
postgres_conn.close()
