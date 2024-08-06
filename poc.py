from datetime import datetime

import numpy as np
import pandas as pd
import psycopg2
from dateutil.relativedelta import relativedelta
from trino.dbapi import connect

with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS org1234567").fetchall()

bucket = "mskarbek-glue"
table_path = f"s3://{bucket}/data/parquet/org1234567/AWS"
sql = f"""
CREATE TABLE IF NOT EXISTS hive.org1234567.fake_line_items (
    name varchar,
    number double,
    start timestamp,
    year varchar,
    month varchar
    )
    WITH(
        external_location = '{table_path}',
        format = 'PARQUET',
        partitioned_by=ARRAY['year', 'month']
    )
"""

with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute(sql).fetchall()


df = pd.DataFrame(
    data={
        "name": ["hello"] * 50,
        "number": np.random.random(50),
        "start": [datetime.now() - relativedelta(hours=x) for x in range(50)],
        "year": ["2024"] * 50,
        "month": ["08"] * 50,
    }
)

path = f"{table_path}/year=2024/month=08"
filename = "file01.parquet"

df.to_parquet(f"{path}/{filename}", allow_truncated_timestamps=True, coerce_timestamps="ms", index=False)

with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute("CALL system.sync_partition_metadata('org1234567', 'fake_line_items', 'FULL')").fetchall()


table_path = f"s3://{bucket}/data/parquet/daily/org1234567/AWS"
sql = f"""
CREATE TABLE IF NOT EXISTS hive.org1234567.fake_line_items_daily (
    name varchar,
    number double,
    start timestamp,
    year varchar,
    month varchar
) WITH (
    external_location = '{table_path}',
    format = 'PARQUET',
    partitioned_by=ARRAY['year', 'month']
)
"""
with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute(sql).fetchall()

daily_df = df.groupby(pd.Grouper(key="start", freq="D")).agg(
    {"name": ["max"], "number": ["sum"], "year": ["max"], "month": ["max"]}
)
daily_df.columns = daily_df.columns.droplevel(1)
daily_df.reset_index(inplace=True)
path = f"{table_path}/year=2024/month=08"
daily_df.to_parquet(f"{path}/{filename}", allow_truncated_timestamps=True, coerce_timestamps="ms", index=False)

with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute("CALL system.sync_partition_metadata('org1234567', 'fake_line_items_daily', 'FULL')").fetchall()

sql = """
CREATE TABLE IF NOT EXISTS hive.org1234567.fake_line_items_summary (
    name varchar,
    number double,
    start timestamp,
    year varchar,
    month varchar
) WITH (
    format = 'PARQUET',
    partitioned_by=ARRAY['year', 'month']
)
"""
with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute(sql).fetchall()

sql = """
INSERT INTO hive.org1234567.fake_line_items_summary (
    name, number, start, year, month
) SELECT
    name, number, start, year, month
FROM hive.org1234567.fake_line_items_daily
"""
with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute(sql).fetchall()


with psycopg2.connect(dbname="postgres", user="postgres", password="postgres", host="localhost", port="15432") as conn:
    cur = conn.cursor()
    cur.execute("CREATE TABLE test (id serial PRIMARY KEY, name varchar, num double precision, start timestamp);")

sql = """
INSERT INTO postgres.public.test (
    name, num, start
) SELECT
    name, number, start
FROM hive.org1234567.fake_line_items_daily
"""
with connect(host="localhost", port=8080, user="admin", catalog="hive", schema="org1234567") as con:
    cur = con.cursor()
    cur.execute(sql).fetchall()
