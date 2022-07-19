#! /usr/bin/env python3
import datetime
import json
import logging
import os
import sys
from multiprocessing import Process
from multiprocessing import Queue

import psycopg2
from app_common_python import LoadedConfig
from dateutil.relativedelta import relativedelta
from psycopg2 import ProgrammingError
from psycopg2.errors import ForeignKeyViolation
from psycopg2.extras import RealDictCursor


logging.basicConfig(
    format="%(processName)s (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger(os.path.basename(sys.argv[0] or "copy_ocp_aws_azure_data_console"))


def connect():
    engine = "postgresql"
    app = os.path.basename(sys.argv[0])

    if bool(os.environ.get("DEVELOPMENT", False)):
        user = os.environ.get("DATABASE_USER")
        passwd = os.environ.get("DATABASE_PASSWORD")
        host = os.environ.get("POSTGRES_SQL_SERVICE_HOST")
        port = os.environ.get("POSTGRES_SQL_SERVICE_PORT")
        db = os.environ.get("DATABASE_NAME")
    else:
        user = LoadedConfig.database.username
        passwd = LoadedConfig.database.password
        host = LoadedConfig.database.hostname
        port = LoadedConfig.database.port
        db = LoadedConfig.database.name

    url = f"{engine}://{user}:{passwd}@{host}:{port}/{db}?sslmode=prefer&application_name={app}"
    LOG.info(f"Connecting to {db} at {host}:{port} as {user}")

    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _execute(conn, sql, params=None):
    cur = conn.cursor()
    LOG.debug(cur.mogrify(sql, params).decode("utf-8"))
    cur.execute(sql, params)
    return cur


def get_ocpawsazure_tables(conn):
    sql = """
with basetable_info as (
select t.relname::text as "basetable_name",
       array_agg(tc.attname::text order by tc.attnum) as "basetable_cols"
  from pg_class t
  join pg_namespace n
    on n.oid = t.relnamespace
  join pg_attribute tc
    on tc.attrelid = t.oid
   and tc.attnum > 0
 where n.nspname = 'template0'
   and t.relkind = 'r'
   and t.relname ~ '^reporting_ocp(aws|azure)costlineitem.*_daily_summary$'
 group
    by t.relname
),
partable_info as (
select t.relname::text as "partable_name",
       array_agg(tc.attname::text order by tc.attnum) as "partable_cols"
  from pg_class t
  join pg_namespace n
    on n.oid = t.relnamespace
  join pg_attribute tc
    on tc.attrelid = t.oid
   and tc.attnum > 0
 where n.nspname = 'template0'
   and t.relkind = 'p'
   and t.relname ~ '^reporting_ocp(aws|azure)costlineitem.*_daily_summary_p$'
 group
    by t.relname
)
select bi.basetable_name,
       pi.partable_name,
       pi.partable_cols
  from partable_info pi
  join basetable_info bi
    on bi.basetable_name || '_p' = pi.partable_name;
"""
    LOG.info("Getting ocp on AWS/Azure base table and partition table info from template schema...")
    tables = _execute(conn, sql).fetchall()

    return tables


def get_customer_schemata(conn):
    sql = """
select t.schema_name
  from public.api_tenant t
  join public.api_customer c
    on c.schema_name = t.schema_name
 where t.schema_name ~ '^acct'
   and exists (select 1
                 from public.api_provider p
                where p.customer_id = c.id
                  and (p.type ~ '^AWS' or p.type ~ '^Azure' or p.type ~ '^OCP'))
 order by 1;
"""
    LOG.info("Getting all customer schemata...")
    return [r["schema_name"] for r in _execute(conn, sql).fetchall()]


def drop_partitions(conn, schema_name, partitioned_table):
    drop_sql = f"""
delete
  from {schema_name}.partitioned_tables
 where schema_name = %s
   and partition_of_table_name = %s
   and partition_parameters->>'default' = 'false';
"""
    LOG.info(f"Dropping partitions for {schema_name}.{partitioned_table}")
    _execute(conn, drop_sql, (schema_name, partitioned_table))


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


def get_table_min(conn, schema_name, table_name):
    sql = f"""
select min(usage_start)::date as "min_start"
  from {schema_name}.{table_name};
"""
    LOG.info(f"Getting the minimum table start from {schema_name}.{table_name}")
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


def copy_data(conn, schema_name, dest_table, dest_cols, source_table):
    copy_sql = """
insert
  into {schema_name}.{partable_name} ({ins_cols})
select {sel_cols}
  from {schema_name}.{basetable_name}
;
"""

    sel_cols = ins_cols = ", ".join(dest_cols)
    sql = copy_sql.format(
        schema_name=schema_name,
        partable_name=dest_table,
        ins_cols=ins_cols,
        sel_cols=sel_cols,
        basetable_name=source_table,
    )
    LOG.info(f"Copying data from {schema_name}.{source_table} to {schema_name}.{dest_table}")
    cur = _execute(conn, sql)
    records_copied = cur.rowcount
    LOG.info(f"Copied {records_copied} records to {schema_name}.{dest_table}")

    return records_copied


def process_ocpawsazure_tables(schema_queue):  # noqa
    with connect() as conn:
        while True:
            msg = schema_queue.get()
            if msg == "DONE":
                LOG.info("End of queue found!")
                break

            work_data = json.loads(msg)
            schema = work_data["schema"]
            table_info = work_data["table_info"]
            tnum = work_data["table_num"]
            ttot = work_data["table_tot"]
            LOG.info(
                f"***** Running copy against schema {schema}.{table_info['basetable_name']} ({tnum}/{ttot}) *****"
            )

            LOG.info(f"Processing {schema}.{table_info['basetable_name']}")
            _execute(conn, f"set search_path = {schema}, public;")
            try:
                partable_min_date = get_table_min(conn, schema, table_info["basetable_name"])
                drop_partitions(conn, schema, table_info["partable_name"])
                get_or_create_partitions(conn, schema, table_info["partable_name"], partable_min_date)
            except ProgrammingError as p:
                LOG.warning(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Skip processing "
                    + f"for {schema}.{table_info['basetable_name']}."
                )
                conn.rollback()
                continue
            except Exception as e:
                conn.rollback()
                LOG.warning(f"VERY WARNING :: {e.__class__.__name__} :: {e}")
                continue
            else:
                try:
                    conn.commit()
                except Exception as x1:
                    LOG.warning(
                        f"{x1.__class__.__name__} :: {x1}{os.linesep}Skip processing "
                        + f"for {schema}.{table_info['basetable_name']}."
                    )
                    conn.rollback()
                    continue

            try:
                # copy data earlier than the threshold since it should be static.
                copy_data(
                    conn,
                    schema,
                    table_info["partable_name"],
                    table_info["partable_cols"],
                    table_info["basetable_name"],
                )
            except (ProgrammingError, ForeignKeyViolation) as p:
                LOG.warning(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Rolling back copy transaction "
                    + f"for {schema}.{table_info['basetable_name']}."
                )
                conn.rollback()
            except Exception as e:
                conn.rollback()
                LOG.warning(f"VERY WARNING :: {e.__class__.__name__} :: {e}")
            else:
                try:
                    conn.commit()
                except Exception as x1:
                    LOG.warning(
                        f"{x1.__class__.__name__} :: {x1}{os.linesep}Rollback copy transaction on COMMIT exception "
                        + f"for {schema}.{table_info['basetable_name']}."
                    )
                    conn.rollback()


def main():
    # get customer schemata
    schemata = tables = None
    with connect() as conn:
        schemata = get_customer_schemata(conn)
        tables = get_ocpawsazure_tables(conn)

    if schemata and tables:
        # Combine for the individual job work
        target_tables = [{"schema": schema, "table_info": table_info} for schema in schemata for table_info in tables]
        t_tot = len(target_tables)
        del schemata
        del tables

        # start worker processes
        max_workers = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("NUM_JOB_WORKERS", 1))
        if max_workers > t_tot:
            max_workers = t_tot

        schema_queues = []
        workers = []
        for wnum in range(max_workers):
            LOG.info(f"Creating worker {len(workers)}")
            schema_queues.append(Queue())
            workers.append(
                Process(target=process_ocpawsazure_tables, name=f"copy_worker_{wnum}", args=((schema_queues[-1]),))
            )
            workers[-1].daemon = True
            workers[-1].start()

        # load worker queues
        LOG.info("Filling worker queues")
        for t_num, data in enumerate(target_tables):
            q_num = t_num % max_workers
            data["table_num"] = t_num + 1
            data["table_tot"] = t_tot
            schema_queues[q_num].put(json.dumps(data))

        # mark worker queue end
        for q in schema_queues:
            q.put("DONE")

        # wait on all workers
        LOG.info("Waiting on workers...")
        for wrkr in workers:
            wrkr.join()
    else:
        LOG.info("No schemata or tables found matching the criteria.")


if __name__ == "__main__":
    main()
