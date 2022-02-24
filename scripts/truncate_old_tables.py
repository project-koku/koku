#! /usr/bin/env python3.8
import datetime
import logging
import os
import sys
from decimal import Decimal

import psycopg2
from app_common_python import LoadedConfig
from psycopg2.extras import NamedTupleCursor

my_path = os.path.abspath(__file__)
my_path = os.path.dirname(os.path.dirname(my_path))
sys.path.append(os.path.join(my_path, "koku"))

from masu import processor as masup  # noqa


UNLEASH_CLIENT = masup.UNLEASH_CLIENT
enable_trino_processing = masup.enable_trino_processing


logging.basicConfig(
    format="truncate_old_tables (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO")),
)
LOG = logging.getLogger("truncate_old_tables")


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


def get_account_info(conn):
    sql = """
select p."uuid" as source_uuid,
       p."type" as source_type,
       c.schema_name as "account"
  from public.api_provider p
  join public.api_customer c
    on c.id = p.customer_id
 where p."type" in ('Azure', 'Azure-local')
;
"""
    res = {}
    for rec in _execute(conn, sql):
        res.setdefault(rec.account, []).append(rec)

    return res


def get_trino_enabled_accounts(conn):
    enabled_accounts = []
    for account, sources in get_account_info(conn).items():
        if all(enable_trino_processing(s.source_uuid, s.source_type, account) for s in sources):
            enabled_accounts.append(account)

    return enabled_accounts


def validate_tables(conn):
    accounts = get_trino_enabled_accounts(conn)
    if not accounts:
        return ()

    tables = [
        # "reporting_ocpusagelineitem",
        # "reporting_ocpusagelineitem_daily",
        # "reporting_awscostentrylineitem",
        # "reporting_awscostentrylineitem_daily",
        # "reporting_azurecostentrylineitem",
        "reporting_azurecostentrylineitem_daily"
    ]

    sql = """
with accounts(acct) as (
select unnest(%s)
),
tables(tab) as (
select unnest(%s)
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
    with conn.cursor() as cur:
        cur.execute(sql, (accounts, tables))
        res = cur.fetchall()

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
    LOG.info("Truncate job starting")
    missing = 0
    exists = 0
    current = 0
    res = validate_tables(conn)
    total = len(res)

    for rec in res:
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
    LOG.info(f"Truncate job completed. Duration: {decode_timedelta(job_end - job_start)}")
    LOG.info(f"Tables missing: {missing}; Tables truncated: {exists}; Total: {total}")


def main():
    UNLEASH_CLIENT.initialize_client()

    with connect() as conn:
        handle_truncate(conn)
        conn.rollback()


if __name__ == "__main__":
    main()

    # accounts = sorted(
    #     {
    #         "acct1508484",
    #         "acct7179461",
    #         "acct798863",
    #         "acct841855",
    #         "acct853019",
    #         "acct941133",
    #         "acct1051497",
    #         "acct1070899",
    #         "acct1157386",
    #         "acct1192214",
    #         "acct1458658",
    #         "acct5258694",
    #         "acct5463389",
    #         "acct5497402",
    #         "acct5618348",
    #         "acct5618348",
    #         "acct5967621",
    #         "acct6153718",
    #         "acct6164464",
    #         "acct6168722",
    #         "acct6213188",
    #         "acct6243247",
    #         "acct6252310",
    #         "acct6289401",
    #         "acct6313207",
    #         "acct6313207",
    #         "acct6313207",
    #         "acct6335545",
    #         "acct6341198",
    #         "acct6351153",
    #         "acct6357256",
    #         "acct6366070",
    #         "acct6399820",
    #         "acct6399820",
    #         "acct6410599",
    #         "acct6501002",
    #         "acct6753467",
    #         "acct6760377",
    #         "acct6766577",
    #         "acct6841665",
    #         "acct6867782",
    #         "acct6867782",
    #         "acct6932064",
    #         "acct6966525",
    #         "acct6987056",
    #         "acct7003175",
    #         "acct7074750",
    #         "acct7079262",
    #         "acct7096714",
    #         "acct7098055",
    #         "acct7098705",
    #         "acct7099829",
    #         "acct7101499",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct531488",
    #         "acct7107950",
    #         "acct7108119",
    #         "acct7108970",
    #         "acct7112432",
    #         "acct7113273",
    #         "acct7117526",
    #         "acct7127948",
    #         "acct7128681",
    #         "acct7152267",
    #         "acct7170105",
    #         "acct7229729",
    #         "acct7238905",
    #         "acct7268919",
    #         "acct7270635",
    #         "acct7272373",
    #         "acct7316731",
    #         "acct7378535",
    #         "acct7386846",
    #         "acct7398034",
    #         "acct7439217",
    #         "acct7517753",
    #         "acct7569812",
    #         "acct7597468",
    #         "acct7620038",
    #         "acct7632642",
    #         "acct7650990",
    #         "acct7688563",
    #         "acct8148553",
    #         # 'acct1116156',
    #         "acct908376",
    #     }
    # )
