#! /usr/bin/env python3.8
import datetime
import json
import logging
import os
import sys

import psycopg2
from dateutil.relativedelta import relativedelta
from psycopg2 import ProgrammingError
from psycopg2.extras import RealDictCursor


logging.basicConfig(
    format="%(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger(os.path.basename(sys.argv[0] or "copy_aws_matview_data_console"))


def connect():
    engine = os.environ.get("DATABASE_ENGINE", "postgresql")
    user = os.environ.get("DATABASE_USER", "postgres")
    passed = os.environ.get("DATABASE_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_SQL_SERVICE_HOST", "db")
    port = os.environ.get("POSTGRES_SQL_SERVICE_PORT", "5432")
    db = os.environ.get("DATABASE_NAME", "postgres")
    app = os.path.basename(sys.argv[0])
    url = f"{engine}://{user}:{passed}@{host}:{port}/{db}?sslmode=require&application_name={app}"

    LOG.info(f"Connecting to {db} at {host}:{port} as {user}")

    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _execute(conn, sql, params=None):
    cur = conn.cursor()
    LOG.debug(cur.mogrify(sql, params).decode("utf-8"))
    cur.execute(sql, params)
    return cur


def get_aws_matviews(conn):
    sql = """
with matview_info as (
select m.relname::text as "matview_name",
       array_agg(mc.attname::text order by mc.attnum) as "matview_cols"
  from pg_class m
  join pg_attribute mc
    on mc.attrelid = m.oid
   and mc.attnum > 0
 where m.relkind = 'm'
   and m.relnamespace = 'template0'::regnamespace
   and m.relname ~ '^reporting_aws'
 group
    by m.relname
),
partable_info as (
select t.relname::text as "partable_name",
       array_agg(tc.attname::text order by tc.attnum) as "partable_cols"
  from pg_class t
  join pg_attribute tc
    on tc.attrelid = t.oid
   and tc.attnum > 0
 where t.relkind = 'p'
   and t.relnamespace = 'template0'::regnamespace
   and t.relname ~ '^reporting_aws.*_p$'
 group
    by t.relname
)
select mi.matview_name,
       pi.partable_name,
       pi.partable_cols
  from partable_info pi
  join matview_info mi
    on mi.matview_name || '_p' = pi.partable_name;
"""
    LOG.info("Getting materialized view and partition table info from template schema...")
    matviews = _execute(conn, sql).fetchall()

    return matviews


def get_customer_schemata(conn):
    sql = """
select schema_name
  from public.api_tenant
 where schema_name ~ '^acct';
"""
    LOG.info("Getting all customer schemata...")
    return [r["schema_name"] for r in _execute(conn, sql).fetchall()]


def get_or_create_partitions(conn, schema_name, partitioned_table, start_date):
    get_sql = f"""
select id
  from {schema_name}.partitioned_tables
 where schema_name = %s
   and table_name = %s
   and partition_of_table_name = %s;
"""
    ins_sql = f"""
insert
  into {schema_name}.partitioned_tables
       (
           schema_name,
           table_name,
           partition_of_table_name,
           partition_type,
           partition_col,
           partition_parameters,
           active
       )
values (
           %(schema_name)s,
           %(table_name)s,
           %(partition_of_table_name)s,
           %(partition_type)s,
           %(partition_col)s,
           %(partition_parameters)s,
           %(active)s
       )
returning id;
"""
    one_month = relativedelta(months=1)
    partition_start = start_date.replace(day=1)
    partition_stop = datetime.date.today().replace(day=1)
    partition_parameters = {"default": False}
    table_partition_rec = {
        "schema_name": schema_name,
        "table_name": None,
        "partition_of_table_name": partitioned_table,
        "partition_type": "range",
        "partition_col": "usage_start",
        "partition_parameters": None,
        "active": True,
    }

    while partition_start <= partition_stop:
        partition_end = partition_start + one_month
        partition_name = f"{partitioned_table}_{partition_start.strftime('%Y_%m')}"
        if (_execute(conn, get_sql, (schema_name, partition_name, partitioned_table)).fetchone() or {"id": None})[
            "id"
        ]:
            LOG.info(f"Found partition {partition_name}")
        else:
            LOG.info(f"Creating partition {partition_name}")
            table_partition_rec["table_name"] = partition_name
            partition_parameters["from"] = str(partition_start)
            partition_parameters["to"] = str(partition_end)
            table_partition_rec["partition_parameters"] = json.dumps(partition_parameters)
            _execute(conn, ins_sql, table_partition_rec)

        partition_start = partition_end


def get_matview_min(conn, schema_name, matview_name):
    sql = f"""
select min(usage_start)::date as "min_start"
  from {schema_name}.{matview_name};
"""
    LOG.info(f"Getting the minimum matview start from {schema_name}.{matview_name}")
    min_start = _execute(conn, sql).fetchone()["min_start"] or datetime.date.today().replace(day=1)
    return min_start


def get_partable_min(conn, schema_name, partable_name):
    sql = f"""
select min(usage_start)::date as "min_start"
  from {schema_name}.{partable_name};
"""
    LOG.info(f"Getting the minimum partition start from {schema_name}.{partable_name}")
    min_start = _execute(conn, sql).fetchone()["min_start"] or datetime.date.today().replace(day=1)
    return min_start


def copy_data(conn, schema_name, dest_table, dest_cols, source_view, min_start):
    copy_sql = """
insert
  into {schema_name}.{partable_name} ({ins_cols})
select uuid_generate_v4(), {sel_cols}
  from {schema_name}.{matview_name} mv
 where mv.usage_start < coalesce(%(min_start)s, date_trunc('month', current_date)::date);
"""

    ins_cols = ", ".join(dest_cols)
    sel_cols = ", ".join(c if c != "blended_cost" else "null" for c in dest_cols if c != "id")
    sql = copy_sql.format(
        schema_name=schema_name,
        partable_name=dest_table,
        ins_cols=ins_cols,
        sel_cols=sel_cols,
        matview_name=source_view,
    )
    LOG.info(f"Copying data earlier than {min_start} from {schema_name}.{source_view} to {schema_name}.{dest_table}")
    cur = _execute(conn, sql, {"min_start": min_start})
    records_copied = cur.rowcount
    LOG.info(f"Copied {records_copied} records")

    return records_copied


def process_aws_matviews(conn, schemata, matviews):
    LOG.info("This script is part of Jira ticket COST-1976 https://issues.redhat.com/browse/COST-1976")
    LOG.info("This script is speficically for sub-task COST-1979 https://issues.redhat.com/browse/COST-1979")

    for schema in schemata:
        LOG.info(f"***** Running copy against schema {schema} *****")
        for matview_info in matviews:
            LOG.info(f"Processing {schema}.{matview_info['matview_name']}")
            copy_threshold_date = get_partable_min(conn, schema, matview_info["partable_name"])
            partable_min_date = get_matview_min(conn, schema, matview_info["matview_name"])
            try:
                get_or_create_partitions(conn, schema, matview_info["partable_name"], partable_min_date)
            except ProgrammingError as p:
                LOG.error(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Skip processing "
                    + f"for {schema}.{matview_info['matview_name']}."
                )
                conn.rollback()
                continue
            except Exception as e:
                LOG.error(f"{e.__class__.__name__} :: {e}")
                raise e
            else:
                conn.commit()

            try:
                # copy data earlier than the threshold since it should be static.
                copy_data(
                    conn,
                    schema,
                    matview_info["partable_name"],
                    matview_info["partable_cols"],
                    matview_info["matview_name"],
                    copy_threshold_date,
                )
            except ProgrammingError as p:
                LOG.error(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Rolling back copy transaction "
                    + f"for {schema}.{matview_info['matview_name']}."
                )
                conn.rollback()
            except Exception as e:
                LOG.error(f"{e.__class__.__name__} :: {e}")
                raise e
            else:
                conn.commit()


def main():
    with connect() as conn:
        matviews = get_aws_matviews(conn)
        schemata = get_customer_schemata(conn)
        conn.rollback()  # close any open tx from selects

        process_aws_matviews(conn, schemata, matviews)


if __name__ == "__main__":
    main()
