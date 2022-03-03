#! /usr/bin/env python3.8
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
import logging
import os
import sys
from decimal import Decimal

import psycopg2
from lite.config import CONFIGURATOR
from psycopg2.extras import NamedTupleCursor


# Struct to hold predefined, static settings
# This is here so the django.settings module does not have to be imported.
logging.basicConfig(
    format="truncate_ocpawsazure_tables (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging.INFO,
)
LOG = logging.getLogger("truncate_ocpawsazure_tables")


def connect():
    engine = "postgresql"
    app = os.path.basename(sys.argv[0])

    user = CONFIGURATOR.get_database_user()
    passwd = CONFIGURATOR.get_database_password()
    host = CONFIGURATOR.get_database_host()
    port = CONFIGURATOR.get_database_port()
    db = CONFIGURATOR.get_database_name()

    url = f"{engine}://{user}:{passwd}@{host}:{port}/{db}?sslmode=prefer&application_name={app}"
    LOG.info(f"Connecting to {db} at {host}:{port} as {user}")

    return psycopg2.connect(url, cursor_factory=NamedTupleCursor)


def _execute(conn, sql, params=None):
    cur = conn.cursor()
    LOG.debug(cur.mogrify(sql, params).decode("utf-8"))
    cur.execute(sql, params)
    return cur


def get_valid_tables(conn):
    sql = """
with accounts(acct) as (
select schema_name
  from public.api_tenant
 where schema_name != 'public'
),
tables(tab) as (
select tabl
  from (
      values ('reporting_ocpawscostlineitem_project_daily_summary'),
             ('reporting_ocpawscostlineitem_daily_summary'),
             ('reporting_ocpazurecostlineitem_project_daily_summary'),
             ('reporting_ocpazurecostlineitem_daily_summary')
  ) tabls(tabl)
),
obj_check as (
select a.acct as p_schema,
       t.tab as p_table
  from accounts a
 cross
  join tables t
)
select ck.p_schema,
       ck.p_table,
       n.nspname as exists_schema,
       c.relname as exists_table
  from obj_check ck
  left
  join pg_namespace n
    on n.nspname = ck.p_schema
  left
  join pg_class c
    on c.relnamespace = n.oid
   and c.relname = ck.p_table
;
"""
    res = _execute(conn, sql).fetchall()

    return res


def decode_timedelta(delta):
    raw = Decimal(str(delta.total_seconds()))
    hours = int(raw // 3600)
    minutes = int(raw // 60)
    seconds = int(raw % 60)
    mseconds = int((raw - int(raw)) * 1000000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{mseconds:06}"


def handle_truncate(conn):
    job_start = datetime.datetime.utcnow()
    LOG.info("OCP on AWS/Azure truncate job starting")
    missing = 0
    exists = 0
    current = 0
    target_tables = get_valid_tables(conn)
    total = len(target_tables)
    LOG.info(f"Found {total} tables")

    for rec in target_tables:
        current += 1
        if rec.exists_schema is None or rec.exists_table is None:
            missing += 1
            LOG.info(f"Table {rec.p_schema}.{rec.p_table} does not exist. ({current}/{total})")
            continue

        exists += 1
        sql = f"TRUNCATE TABLE {rec.exists_schema}.{rec.exists_table} ;"
        LOG.info(f"Truncating {rec.exists_schema}.{rec.exists_table} ({current}/{total})")
        try:
            _execute(conn, sql)
        except Exception as e:
            LOG.error(f"{type(e).__name__}: {e}")
            conn.rollback()
        else:
            LOG.info("    Commit truncate.")
            conn.commit()

    job_end = datetime.datetime.utcnow()
    LOG.info(f"OCP on AWS/Azure truncate job completed. Duration: {decode_timedelta(job_end - job_start)}")
    LOG.info(f"Tables missing: {missing}; Tables truncated: {exists}; Total: {total}")


def main():
    with connect() as conn:
        handle_truncate(conn)
        conn.rollback()


if __name__ == "__main__":
    main()
