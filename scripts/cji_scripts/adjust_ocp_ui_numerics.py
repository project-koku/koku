#! /usr/bin/env python3.8
import logging
import os
import sys

import psycopg2
from app_common_python import LoadedConfig
from psycopg2 import ProgrammingError
from psycopg2.extras import RealDictCursor


logging.basicConfig(
    format="%(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger(os.path.basename(sys.argv[0] or "adjust_ocp_ui_numerics"))


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


def get_ocp_partables(conn):
    sql = """
select table_schema::text,
       table_name::text,
       array_agg(column_name::text order by ordinal_position)::text[] as alter_cols
  from information_schema.columns
 where (table_schema = 'template0' or table_schema ~ '^acct')
   and table_name ~ '^reporting_ocp_.+_p$'
   and data_type = 'numeric'
   and numeric_precision is not null
   and numeric_precision < 33
 group
    by 1, 2;
"""
    LOG.info("Getting partition table info from information_schema...")
    partables = _execute(conn, sql).fetchall()

    return partables


def alter_partable(conn, partable):
    alter_table_sql = [f"""alter table {partable['table_schema']}.{partable['table_name']}"""]
    if partable["alter_cols"]:
        alter_column_sql = """      alter column {} set data type numeric(33, 15) """

        for col in partable["alter_cols"]:
            alter_table_sql.append(alter_column_sql.format(col))

        sep = f",{os.linesep}"
        sql = f"{alter_table_sql[0]}{os.linesep}{sep.join(alter_table_sql[1:])} ;"

        LOG.info(f"""    altering columns {', '.join(partable["alter_cols"])} to data type numeric(33,15)""")
        _execute(conn, sql)


def process_ocp_partables(conn, partables):  # noqa
    LOG.info("This script is part of Jira ticket COST-1976 https://issues.redhat.com/browse/COST-1976")
    LOG.info("This script is speficically for sub-task COST-1979 https://issues.redhat.com/browse/COST-1979")

    i = 0
    tot = len(partables)
    for partable in partables:
        i += 1
        LOG.info(f"Running alter table against {partable['table_schema']}.{partable['table_name']} ({i} / {tot})")
        try:
            alter_partable(conn, partable)
        except ProgrammingError as p:
            LOG.warning(
                f"{p.__class__.__name__} :: {p}{os.linesep}Skip processing "
                + f"for {partable['table_schema']}.{partable['table_name']}."
            )
            conn.rollback()
            continue
        except Exception as e:
            conn.rollback()
            LOG.warning(f"VERY WARNING :: {e.__class__.__name__} :: {e}")
            continue


def main():
    with connect() as conn:
        partables = get_ocp_partables(conn)
        conn.rollback()  # close any open tx from selects

        process_ocp_partables(conn, partables)


if __name__ == "__main__":
    main()
