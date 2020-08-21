import os

import prestodb

PRESTO_HOST = os.environ.get("PRESTO_HOST", "localhost")
PRESTO_USER = os.environ.get("PRESTO_USER", "admin")
PRESTO_CATALOG = os.environ.get("PRESTO_CATALOG", "hive")
PRESTO_SCHEMA = os.environ.get("PRESTO_SCHEMA", "default")

try:
    PRESTO_PORT = int(os.environ.get("PRESTO_PORT", "8080"))
except ValueError:
    PRESTO_PORT = 8080


conn = prestodb.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema="default")

bucket = "koku-bucket"
account = "10001"
provider_uuid = "9a37b241-4066-432d-93d7-2aed87a74742"
year = "2020"
month = "08"
s3_path = f"{bucket}/data/parquet/{account}/{provider_uuid}/{year}/{month}/"

table_name = f"default.aws_data_{account}_{provider_uuid.replace('-', '_')}"

sql = f"CREATE TABLE IF NOT EXISTS {table_name} ("

aws_columns = []
column_file = "/Users/curtisd/projects/repos/koku/scripts/columns.txt"
with open(column_file, "r") as fd:
    for line in fd:
        line = line.strip()
        aws_columns.append(line)

# aws_columns.sort()

for idx, col in enumerate(aws_columns):
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
    if idx < (len(aws_columns) - 1):
        sql += ","

sql += f") WITH(external_location = 's3a://{s3_path}', format = 'PARQUET');"

print(sql)

# cur = conn.cursor()
# cur.execute(sql)


# cur = conn.cursor()
# cur.execute(
#    "SELECT * FROM default.aws_data_10001_022e9fc1-4897-49db-bc9f-1a91e4607b3b_2020_08")
# rows = cur.fetchall()

# for row in rows:
#    print(row)
