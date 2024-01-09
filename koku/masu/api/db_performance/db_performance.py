#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os
from decimal import Decimal

import psycopg2
from psycopg2.errors import ProgrammingError
from psycopg2.extras import RealDictCursor
from sqlparse import format as sql_format
from sqlparse import parse as sql_parse
from sqlparse import split as sql_split


RELEASE = 0
MAJOR = 1
MINOR = 2

TERMINATE_ACTION = "terminate"
CANCEL_ACTION = "cancel"

SERVER_VERSION = []

LOG = logging.getLogger(__name__)


class DBPerformanceStats:
    def __init__(self, username, configurator, application_name="database_performance_stats"):
        self.conn = None
        self.username = username
        self.config = configurator
        self.app_db_name = configurator.get_database_name()
        self.application_name = application_name
        self.read_only = True
        self._connect()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, extype, exval, extrace):
        self._disconnect()

    def __del__(self):
        self._disconnect()

    def _disconnect(self):
        if self.conn and not self.conn.closed:
            self.conn.rollback()
            self.conn.close()
            self.conn = None

    def _connect(self):
        # engine = "postgresql"
        if not self.conn or self.conn.closed:
            conn_args = {
                "user": self.config.get_database_user(),
                "password": self.config.get_database_password(),
                "host": self.config.get_database_host(),
                "port": self.config.get_database_port(),
                "dbname": self.config.get_database_name(),
                "application_name": self.application_name,
            }
            if self.config.get_database_ca():
                ssl_opts = {"sslmode": "verify-full", "sslrootcert": self.config.get_database_ca_file()}
            else:
                ssl_opts = {"sslmode": "prefer"}
            conn_args.update(ssl_opts)

            LOG.info(self._prep_log_message("Connecting to {dbname} at {host}:{port} as {user}".format(**conn_args)))
            self.conn = psycopg2.connect(cursor_factory=RealDictCursor, **conn_args)
            self.conn.set_session(readonly=True)

    def _execute(self, sql, params=None):
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        try:
            _sql = cur.mogrify(sql, params or None).decode("utf-8")
            LOG.info(self._prep_log_message(f"EXEC SQL:{_sql}"))
            cur.execute(_sql)
        except Exception as e:
            LOG.error(
                self._prep_log_message(f"{type(e).__name__} ERROR:{os.linesep}SQL: {sql}{os.linesep}PARAMS: {params}")
            )
            raise

        return cur

    def _prep_log_message(self, message):
        return f"USER:{self.username} {message}"

    def get_databases(self):
        sql = """
select oid,
       datname
  from pg_database
 where datname !~ '^template'
 order
    by datname
;
"""
        return self._execute(sql).fetchall()

    def get_pg_settings(self, setting_names=None):
        params = {}
        if setting_names:
            where_clause = "            where name = any(%(setting_names)s) "
            params["setting_names"] = list(setting_names)
        else:
            where_clause = ""

        sql = f"""
-- GROUPED PG SETTINGS
select case when s.category_setting_num = 1 then s.category else ''::text end as category,
       s.name,
       s.description,
       s.context,
       s.unit,
       s.setting,
       s.boot_val,
       s.reset_val,
       s.pending_restart
  from (
           select row_number() over (partition by category) as category_setting_num,
                  category,
                  name,
                  coalesce(short_desc, extra_desc) as description,
                  unit,
                  context,
                  setting,
                  boot_val,
                  reset_val,
                  pending_restart
             from pg_settings
{where_clause}
       ) as s
;
"""
        cur = self._execute(sql, params or None)
        return cur.fetchall()

    def get_pg_engine_version(self):
        global SERVER_VERSION
        if not SERVER_VERSION:
            sql = """
-- PARSED PG ENGINE VERSION
select (boot_val::int / 10000::int)::int as "release",
       ((boot_val::int / 100)::int % 100::int)::int as "major",
       (boot_val::int % 100::int)::int as "minor"
  from pg_settings
 where name = 'server_version_num';
"""
            res = self._execute(sql, None).fetchone()
            SERVER_VERSION.extend(res.values())

        return SERVER_VERSION

    def _handle_limit(self, limit, params):
        if isinstance(limit, int) and limit > 0:
            limit_clause = " limit %(limit)s "
            params["limit"] = limit
        else:
            limit_clause = ""

        return limit_clause

    def _handle_offset(self, offset, params):
        if isinstance(offset, int) and offset >= 0:
            offset_clause = " offset %(offset)s "
            params["offset"] = offset
        else:
            offset_clause = ""

        return offset_clause

    def _validate_pg_stat_statements(self):
        sql = """
select oid,
       extversion
  from pg_extension
 where extname = 'pg_stat_statements';
"""
        extn = self._execute(sql, None).fetchone()
        sql = """
select oid
  from pg_class
 where relnamespace = 'public'::regnamespace
   and relname = 'pg_stat_statements'
   and relkind = 'v';
"""
        view = self._execute(sql, None).fetchone()
        ext_exists = bool(extn) and bool(extn.get("oid")) and bool(view) and bool(view.get("oid"))
        ext_version = extn["extversion"] if ext_exists else None
        return (ext_exists, ext_version)

    def get_statement_stats(self, dbname, limit=100, offset=None):
        params = {}

        has_pss, pss_ver = self._validate_pg_stat_statements()
        if not has_pss:
            return [{"Result": "pg_stat_statements extension not installled"}]

        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        col_name_sep = "_" if Decimal(pss_ver) < Decimal("1.8") else "_exec_"
        params["dbname"] = dbname
        sql = f"""
-- STATEMENT STATISTICS
select d.datname as "dbname",
       r.rolname as "user",
       s.calls,
       s.rows,
       s.min{col_name_sep}time as min_exec_time,
       s.mean{col_name_sep}time as mean_exec_time,
       s.max{col_name_sep}time as max_exec_time,
       s.shared_blks_hit,
       s.shared_blks_read,
       s.local_blks_hit,
       s.local_blks_read,
       s.temp_blks_read,
       s.temp_blks_written,
       s.query
  from public.pg_stat_statements s
  join pg_database d
    on d.oid = s.dbid
  join pg_roles r
    on r.oid = s.userid
 where d.datname = %(dbname)s
   and s.userid is not null
 {limit_clause}
 {offset_clause}
;
"""
        LOG.info(self._prep_log_message("requesting data from pg_stat_statements"))
        return self._execute(sql, params).fetchall()

    def get_lock_info(self, dbname, limit=25, offset=None):
        params = {}
        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        params["dbname"] = dbname
        sql = f"""
-- LOCK INFO QUERY
SELECT count(blocking_locks.pid) over (partition by blocking_locks.pid) as blocking_pid_weight,
       blocking_locks.pid::int     AS blocking_pid,
       blocking_activity.usename::text AS blocking_user,
       blocked_locks.pid::int     AS blocked_pid,
       blocked_activity.usename::text  AS blocked_user,
       blocked_activity.query::text    AS blocked_statement,
       blocking_activity.query::text   AS blckng_proc_curr_stmt
  FROM pg_catalog.pg_locks         blocked_locks
  JOIN pg_catalog.pg_stat_activity blocked_activity
    ON blocked_activity.pid = blocked_locks.pid
  JOIN pg_catalog.pg_locks         blocking_locks
    ON blocking_locks.locktype = blocked_locks.locktype
   AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
   AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
   AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
   AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
   AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
   AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
   AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
   AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
   AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
   AND blocking_locks.pid != blocked_locks.pid
  JOIN pg_catalog.pg_stat_activity blocking_activity
    ON blocking_activity.pid = blocking_locks.pid
 WHERE NOT blocked_locks.granted
   AND blocking_activity.datname = %(dbname)s
 ORDER
    BY "blocking_pid_weight" desc,
       blocking_locks.pid
{limit_clause}
{offset_clause}
;
"""
        LOG.info(self._prep_log_message("requsting blocked process information"))
        res = self._execute(sql, params).fetchall()

        return res

    def get_activity(self, dbname, pid=[], state=[], limit=100, offset=None):
        params = {}

        params["dbname"] = dbname
        conditions = ["datname = %(dbname)s", "usename is not null"]
        if pid:
            if not isinstance(pid, list):
                pid = [pid]
            conditions.append("pid = any(%(pid)s::oid[]) ")
            params["pid"] = pid
        if state:
            if not isinstance(state, list):
                state = [state]
            conditions.append("state = any(%(state)s::text[]) ")
            params["state"] = state
        where_clause = f" where {f'{os.linesep}   and '.join(conditions)}"
        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        sql = f"""
-- CONNECTION ACTIVITY QUERY
select datname as "dbname",
       usename as "user",
       pid as "backend_pid",
       application_name as "app_name",
       client_addr as "client_ip",
       backend_start,
       xact_start,
       query_start,
       state_change,
       '('::text || wait_event_type || ') '::text || wait_event as "wait_type_event",
       state,
       case when state = 'active' then now() - query_start else null end::text as "active_time",
       query
  from pg_stat_activity
{where_clause}
{limit_clause}
{offset_clause}
;
"""  # noqa

        LOG.info(self._prep_log_message("requsting connection activity"))
        return self._execute(sql, params).fetchall()

    def explain_sql(self, raw_sql):
        res = []
        for target_sql in sql_split(raw_sql):
            parsed = sql_parse(target_sql)
            sql_type = parsed[0].get_type()
            if sql_type == "UNKNOWN":
                LOG.warning(self._prep_log_message(f"SQL parser returns {sql_type} for statement {target_sql}"))
                raise ProgrammingError("Cannot process statement.")
            elif sql_type in ("CREATE", "DROP", "ALTER"):
                LOG.warning(self._prep_log_message(f"DDL statement detected: {sql_type}"))
                raise ProgrammingError(f"Refusing to process DDL {sql_type}")
            elif sql_type in ("DELETE", "UPDATE", "INSERT"):
                LOG.warning(self._prep_log_message(f"Refusing to process statement type: {sql_type}"))
                raise ProgrammingError(f"Refusing to process statement {sql_type}")

            target_sql = sql_format(
                target_sql, strip_comments=True, keyword_case="lower", identifier_case="lower"
            ).strip()
            if target_sql.startswith("commit") or target_sql.startswith("rollback"):
                raise ProgrammingError("Refusing to process statement;")
            plan = os.linesep.join(rec["QUERY PLAN"] for rec in self._execute(f"EXPLAIN VERBOSE {target_sql}"))
            res.append({"query_plan": plan, "query_text": target_sql})

        return res

    def get_schema_sizes(self, top=0, limit=100, offset=None):
        # This will ONLY run against the primary app database at this time.
        params = {"db_gb": Decimal(1024**3), "top": top}
        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        if top > 0:
            LOG.debug(f"Getting schema size and top {top} tables")
            sql = f"""
select schema_name,
       table_name,
       round(table_size::numeric / %(db_gb)s::numeric, 10) as "table_size_gb",
       round(schema_size::numeric / %(db_gb)s::numeric, 10) as "schema_size_gb"
  from (
           select row_number() over (partition by n.oid order by pg_total_relation_size(t.oid) desc) as rownum,
                  n.nspname as "schema_name",
                  t.relname as "table_name",
                  pg_total_relation_size(t.oid) as "table_size",
                  sum(pg_total_relation_size(t.oid)) over (partition by n.nspname) as "schema_size"
             from pg_namespace n
             join pg_class t
               on t.relnamespace = n.oid
              and t.relkind in ('r', 'p')
            where n.nspname not in ('pg_catalog','information_schema')
       ) as raw_object_sizes
 where "rownum" <= %(top)s
 order
    by "schema_size_gb" desc,
       schema_name,
       "table_size_gb" desc,
       table_name
{limit_clause}
{offset_clause}
;
"""
        else:
            LOG.debug("Getting schema size only")
            sql = f"""
select schema_name,
       round(schema_size::numeric / %(db_gb)s::numeric, 10) as "schema_size_gb"
  from (
           select n.nspname as "schema_name",
                  sum(pg_total_relation_size(t.oid)) as schema_size
             from pg_namespace n
             join pg_class t
               on t.relnamespace = n.oid
              and t.relkind in ('r', 'p')
            where n.nspname not in ('pg_catalog','information_schema')
            group
               by n.nspname
       ) as raw_object_sizes
 order
    by "schema_size_gb" desc,
       schema_name
{limit_clause}
{offset_clause}
;
"""
        return self._execute(sql, params).fetchall()

    def terminate_cancel_backends(self, backends=[], action_type=None):
        if not backends:
            return None

        if action_type not in (TERMINATE_ACTION, CANCEL_ACTION):
            raise ValueError(f"Illegal action_type value '{action_type}'")

        sql = f"""
-- {action_type.upper()} QUERY
select pid,
        pg_{action_type}_backend(pid) as "{action_type}"
    from unnest(%(backends)s::int[]) pid;
"""
        LOG.warning(f"sql:\n\n{sql}\n\n")
        params = {"backends": backends}
        return self._execute(sql, params).fetchall()

    def terminate_backends(self, backends=[]):
        LOG.info(self._prep_log_message(f"Terminating backend pids {backends}"))
        return self.terminate_cancel_backends(backends=backends, action_type=TERMINATE_ACTION)

    def cancel_backends(self, backends=[]):
        LOG.info(self._prep_log_message(f"Cancelling backend pids {backends}"))
        return self.terminate_cancel_backends(backends=backends, action_type=CANCEL_ACTION)

    def pg_stat_statements_reset(self):
        sql = """
-- RESET STATISTICS
select public.pg_stat_statements_reset();
"""
        LOG.info(self._prep_log_message("Clearing pg_stat_statements"))
        self._execute(sql, None)

        return [{"pg_stat_statements_reset": True}]
