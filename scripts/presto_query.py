import os
import sys

import prestodb
import pyarrow.parquet as pq

PRESTO_HOST = os.environ.get("PRESTO_HOST", "localhost")
PRESTO_USER = os.environ.get("PRESTO_USER", "admin")
PRESTO_CATALOG = os.environ.get("PRESTO_CATALOG", "hive")
PRESTO_SCHEMA = os.environ.get("PRESTO_SCHEMA", "default")

parquet_dir = sys.argv[1]

try:
    PRESTO_PORT = int(os.environ.get("PRESTO_PORT", "8080"))
except ValueError:
    PRESTO_PORT = 8080

account = parquet_dir.split("/")[-4]
provider_uuid = parquet_dir.split("/")[-3]

s3_path = parquet_dir.split("parquet_data/", 1)[1]

table_name = f"default.data_{account}_{provider_uuid.replace('-', '_')}"

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

print(sql)

conn = prestodb.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema="default")
cur = conn.cursor()
cur.execute(sql)

rows = cur.fetchall()

cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM {table_name}")
rows = cur.fetchall()

for row in rows:
    print(row)
