#! /usr/bin/env python3.8
import datetime
import logging
import os
import sys
import time
from decimal import Decimal

import psycopg2
from psycopg2.extras import NamedTupleCursor
from UnleashClient import UnleashClient
from UnleashClient.strategies import Strategy

my_path = os.path.abspath(__file__)
my_path = os.path.dirname(os.path.dirname(my_path))
BASE_DIR = os.path.join(my_path, "koku")
sys.path.append(BASE_DIR)

from koku.env import ENVIRONMENT  # noqa
from koku.configurator import CONFIGURATOR  # noqa


LOGGING_LEVEL = getattr(logging, os.environ.get("KOKU_LOG_LEVEL", "INFO"))
logging.basicConfig(
    format="truncate_old_tables (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=LOGGING_LEVEL,
)
LOG = logging.getLogger("truncate_old_tables")


class settings:
    UNLEASH_HOST = CONFIGURATOR.get_feature_flag_host()
    UNLEASH_PORT = CONFIGURATOR.get_feature_flag_port()
    UNLEASH_PREFIX = "https" if str(UNLEASH_PORT) == "443" else "http"
    UNLEASH_URL = f"{UNLEASH_PREFIX}://{UNLEASH_HOST}:{UNLEASH_PORT}/api"
    UNLEASH_TOKEN = CONFIGURATOR.get_feature_flag_token()
    UNLEASH_CACHE_DIR = ENVIRONMENT.get_value("UNLEASH_CACHE_DIR", default=os.path.join(BASE_DIR, "..", ".unleash"))
    ENABLE_PARQUET_PROCESSING = ENVIRONMENT.bool("ENABLE_PARQUET_PROCESSING", default=False)
    ENABLE_TRINO_SOURCES = ENVIRONMENT.list("ENABLE_TRINO_SOURCES", default=[])
    ENABLE_TRINO_ACCOUNTS = ENVIRONMENT.list("ENABLE_TRINO_ACCOUNTS", default=[])
    ENABLE_TRINO_SOURCE_TYPE = ENVIRONMENT.list("ENABLE_TRINO_SOURCE_TYPE", default=[])


class KokuUnleashClient(UnleashClient):
    """Koku Unleash Client."""

    def destroy(self):
        """Override destroy so that cache is not deleted."""
        self.fl_job.remove()
        if self.metric_job:
            self.metric_job.remove()
        self.scheduler.shutdown()


class SchemaStrategy(Strategy):
    def load_provisioning(self) -> list:
        return self.parameters["schema-name"]

    def apply(self, context):
        default_value = False
        if "schema" in context and context["schema"] is not None:
            default_value = context["schema"] in self.parsed_provisioning
        return default_value


strategies = {
    # All new strategies should be added here.
    "schema-strategy": SchemaStrategy
}
headers = {}
if settings.UNLEASH_TOKEN:
    headers["Authorization"] = f"Bearer {settings.UNLEASH_TOKEN}"


UNLEASH_CLIENT = KokuUnleashClient(
    url=settings.UNLEASH_URL,
    app_name="Cost Management",
    environment=ENVIRONMENT.get_value("KOKU_SENTRY_ENVIRONMENT", default="development"),
    instance_id=ENVIRONMENT.get_value("APP_POD_NAME", default="unleash-client-python"),
    custom_headers=headers,
    custom_strategies=strategies,
    cache_directory=settings.UNLEASH_CACHE_DIR,
    verbose_log_level=LOGGING_LEVEL,
)


def trino_enabled_env(source_uuid, source_type, account):  # noqa
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    return bool(
        settings.ENABLE_PARQUET_PROCESSING
        or source_uuid in settings.ENABLE_TRINO_SOURCES
        or source_type in settings.ENABLE_TRINO_SOURCE_TYPE
        or account in settings.ENABLE_TRINO_ACCOUNTS
    )


def trino_enabled_unleash(source_uuid, source_type, account):  # noqa
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    context = {"schema": account, "source-type": source_type, "source-uuid": source_uuid}
    LOG.info(f"Trion enabled unleash check: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("cost-trino-processor", context))


def enable_trino_processing(source_uuid, source_type, account):  # noqa
    """Helper to determine if source is enabled for Trino."""
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    context = {"schema": account, "source-type": source_type, "source-uuid": source_uuid}
    LOG.info(f"enable_trino_processing context: {context}")
    return bool(
        settings.ENABLE_PARQUET_PROCESSING
        or source_uuid in settings.ENABLE_TRINO_SOURCES
        or source_type in settings.ENABLE_TRINO_SOURCE_TYPE
        or account in settings.ENABLE_TRINO_ACCOUNTS
        or UNLEASH_CLIENT.is_enabled("cost-trino-processor", context)
    )


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
    unleash_request = 0
    unleash_limit = 100

    for account, sources in get_account_info(conn).items():
        if unleash_request >= unleash_limit:
            time.sleep(1)
            unleash_request = 0

        enabled_flags = []
        for source in sources:
            res = trino_enabled_env(source.source_uuid, source.source_type, account)
            if not res:
                unleash_res = trino_enabled_unleash(source.source_uuid, source.source_type, account)
                unleash_request += 1

            enabled_flags.append(res or unleash_res)
            # Assumes unleash is set at the schema level
            if unleash_res:
                break

        if all(enabled_flags):
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
