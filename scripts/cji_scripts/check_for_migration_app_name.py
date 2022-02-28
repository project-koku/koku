#! /usr/bin/env python3.8
import logging
import os
import sys

import psycopg2
from app_common_python import LoadedConfig
from psycopg2.extras import NamedTupleCursor


logging.basicConfig(
    format="%(processName)s (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger(os.path.basename(sys.argv[0] or "copy_ocp_aws_azure_data_console"))

MIGRATION_APP_NAME = "koku_db_migration"


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

    # return psycopg2.connect(url, cursor_factory=RealDictCursor)
    return psycopg2.connect(url, cursor_factory=NamedTupleCursor)


def _execute(conn, sql, params=None):
    cur = conn.cursor()
    LOG.debug(cur.mogrify(sql, params).decode("utf-8"))
    cur.execute(sql, params)
    return cur


def check_for_migration_app_name(conn):
    sql = """
select pid,
       application_name,
       client_addr,
       client_hostname,
       backend_start,
       state,
       query
  from pg_stat_activity
 where application_name = %s
 order
    by client_addr,
       pid
;
"""
    LOG.info(f"Checking for application name '{MIGRATION_APP_NAME}'")
    cur = _execute(conn, sql, (MIGRATION_APP_NAME,))
    LOG.info(f"Got {cur.rowcount} rows")
    tmpl = ["", "Record {0}:"]
    tmpl.extend("    {0}: {{1.{0}}}".format(d[0]) for d in cur.description)
    tmpl = os.linesep.join(tmpl)
    for i, rec in enumerate(cur):
        LOG.info(tmpl.format(i + 1, rec))
    LOG.info("Check complete")


def main():
    with connect() as conn:
        check_for_migration_app_name(conn)
        conn.rollback()


if __name__ == "__main__":
    main()
