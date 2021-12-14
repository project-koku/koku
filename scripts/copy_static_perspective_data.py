#! /usr/bin/env python3.8
import datetime
import json
import logging
import os
import sys

import psycopg2
from app_common_python import LoadedConfig
from dateutil.relativedelta import relativedelta
from psycopg2 import ProgrammingError
from psycopg2.errors import ForeignKeyViolation
from psycopg2.extras import RealDictCursor


logging.basicConfig(
    format="%(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger(os.path.basename(sys.argv[0] or "copy_ocpazure_matview_data_console"))


def connect():
    engine = "postgresql"
    app = os.path.basename(sys.argv[0])
    user = LoadedConfig.database.username
    passed = LoadedConfig.database.password
    host = LoadedConfig.database.hostname
    port = LoadedConfig.database.port
    db = LoadedConfig.database.name

    url = f"{engine}://{user}:{passed}@{host}:{port}/{db}?sslmode=prefer&application_name={app}"
    LOG.info(f"Connecting to {db} at {host}:{port} as {user}")

    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _execute(conn, sql, params=None):
    cur = conn.cursor()
    LOG.debug(cur.mogrify(sql, params).decode("utf-8"))
    cur.execute(sql, params)
    return cur


def get_ocpazure_matviews(conn):
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
   and m.relname ~ '^reporting_ocpazure_'
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
   and t.relname ~ '^reporting_ocpazure_.*_p$'
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
select 'template0' as schema_name
 union
select t.schema_name
  from public.api_tenant t
  join public.api_customer c
    on c.schema_name = t.schema_name
 where t.schema_name ~ '^acct'
   and exists (select 1 from public.api_provider p where p.customer_id = c.id
   and (p.type ~ '^Azure' or p.type ~ '^OCP'))
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


def copy_data(conn, schema_name, dest_table, dest_cols, source_view):
    copy_sql = """
insert
  into {schema_name}.{partable_name} ({ins_cols})
select uuid_generate_v4(), {sel_cols}
  from {schema_name}.{matview_name} mv
;
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
    LOG.info(f"Copying data from {schema_name}.{source_view} to {schema_name}.{dest_table}")
    cur = _execute(conn, sql)
    records_copied = cur.rowcount
    LOG.info(f"Copied {records_copied} records")

    return records_copied


def alter_partable(conn, schema, partable_name, alter_cols):
    if alter_cols:
        alter_table_sql = [f"""alter table {schema}.{partable_name}"""]
        alter_column_sql = """alter column {} drop not null"""

        for col in alter_cols:
            alter_table_sql.append(alter_column_sql.format(col))

        sql = f"{os.linesep.join(alter_table_sql)} ;"

        LOG.info(
            f"""##### ALTER TABLE {schema}.{partable_name} :: removing NOT NULL constraint """
            + f"""from columns: {', '.join('"{}"'.format(c) for c in alter_cols)}"""
        )
        _execute(conn, sql)


def data_exists(conn, schema_name, partable_name):
    res = _execute(
        conn, f"select exists(select 1 from {schema_name}.{partable_name})::boolean as data_exists;"
    ).fetchone()
    return res["data_exists"]


def process_ocpazure_matviews(conn, schemata, matviews):  # noqa
    tot = len(schemata)
    for i, schema in enumerate(schemata, start=1):
        LOG.info(f"***** Running copy against schema {schema} ({i} / {tot}) *****")
        _execute(conn, f"set search_path = {schema}, public;")
        for matview_info in matviews:
            LOG.info(f"Processing {schema}.{matview_info['matview_name']}")
            try:
                # alter_partable(conn, schema, matview_info["partable_name"], matview_info["alter_cols"])
                if data_exists(conn, schema, matview_info["partable_name"]):
                    LOG.info(f"Materialized view {schema}.{matview_info['matview_name']} has already been processed.")
                    continue
                partable_min_date = get_matview_min(conn, schema, matview_info["matview_name"])
                # drop_partitions(conn, schema, matview_info["partable_name"])
                get_or_create_partitions(conn, schema, matview_info["partable_name"], partable_min_date)
            except ProgrammingError as p:
                LOG.warning(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Skip processing "
                    + f"for {schema}.{matview_info['matview_name']}."
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
                        + f"for {schema}.{matview_info['matview_name']}."
                    )
                    conn.rollback()
                    continue

            try:
                # copy data earlier than the threshold since it should be static.
                copy_data(
                    conn,
                    schema,
                    matview_info["partable_name"],
                    matview_info["partable_cols"],
                    matview_info["matview_name"],
                )
            except (ProgrammingError, ForeignKeyViolation) as p:
                LOG.warning(
                    f"{p.__class__.__name__} :: {p}{os.linesep}Rolling back copy transaction "
                    + f"for {schema}.{matview_info['matview_name']}."
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
                        + f"for {schema}.{matview_info['matview_name']}."
                    )
                    conn.rollback()


def main():
    with connect() as conn:
        matviews = get_ocpazure_matviews(conn)
        schemata = get_customer_schemata(conn)
        conn.rollback()  # close any open tx from selects

        process_ocpazure_matviews(conn, schemata, matviews)


if __name__ == "__main__":
    main()
