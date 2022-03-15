#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os

import psycopg2
from psycopg2.extras import RealDictCursor


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
        self.application_name = application_name
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

    def _execute(self, sql, params):
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
select oid
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
        return bool(extn) and bool(extn.get("oid")) and bool(view) and bool(view.get("oid"))

    def get_statement_stats(self, limit=100, offset=None):
        params = {}

        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        col_name_sep = "_" if self.get_pg_engine_version()[RELEASE] < 13 else "_exec_"
        sql = f"""
-- STATEMENT STATISTICS
select d.datname as "database",
       r.rolname as "role",
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
  left
  join pg_database d
    on d.oid = s.dbid
  left
  join pg_roles r
    on r.oid = s.userid
 order
    by d.datname,
       s.mean{col_name_sep}time desc
 {limit_clause}
 {offset_clause}
;
"""
        LOG.info(self._prep_log_message("requesting data from pg_stat_statements"))
        if self._validate_pg_stat_statements():
            return self._execute(sql, params).fetchall()
        else:
            return [{"Result": "pg_stat_statements extension not installled"}]

    def get_lock_info(self, limit=None, offset=None):
        params = {}
        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)
        sql = f"""
-- LOCK INFO QUERY
SELECT blocking_locks.pid::int     AS blocking_pid,
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
{limit_clause}
{offset_clause}
;
"""
        LOG.info(self._prep_log_message("requsting blocked process information"))
        res = self._execute(sql, params).fetchall()
        if not res:
            res = [{"Result": "No blocking locks"}]
        return res

    def get_activity(self, pid=[], state=[], include_self=False, limit=250, offset=None):
        params = {}

        conditions = ["datname is not null"]
        if pid:
            include_self = True
            conditions.append("pid = any(%(pid)s::oid[]) ")
            params["pid"] = pid
        if state:
            conditions.append("state = any(%(state)s::text[]) ")
            params["state"] = state
        if not include_self:
            conditions.append("pid != %(mypid)s ")
            params["mypid"] = self.conn.get_backend_pid()
        where_clause = f" where {f'{os.linesep}   and '.join(conditions)}"
        limit_clause = self._handle_limit(limit, params)
        offset_clause = self._handle_offset(offset, params)

        sql = f"""
-- CONNECTION ACTIVITY QUERY
select datname as "database",
       usename as "role",
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
 order
    by datname,
       state,
       extract(epoch from now() - query_start) desc
{limit_clause}
{offset_clause}
;
"""

        LOG.info(self._prep_log_message("requsting connection activity"))
        return self._execute(sql, params).fetchall()


#     def terminate_cancel_backends(self, backends=[], action_type=None):
#         if not backends:
#             return None

#         if action_type not in (TERMINATE_ACTION, CANCEL_ACTION):
#             raise ValueError(f"Illegal action_type value '{action_type}'")

#         sql = f"""
# -- {action_type.upper()} QUERY
# select pid,
#        pg_{action_type}_backend(pid) as "{action_type}"
#   from unnest(%(backends)s::int[]) pid;
# """
#         params = {"backends": backends}
#         return self._execute(sql, params).fetchall()

#     def terminate_backends(self, backends=[]):
#         LOG.info(self._prep_log_message(f"Terminating backend pids {backends}"))
#         return self.terminate_cancel_backends(backends=backends, action_type=TERMINATE_ACTION)

#     def cancel_backends(self, backends=[]):
#         LOG.info(self._prep_log_message(f"Cancellikng backend pids {backends}"))
#         return self.terminate_cancel_backends(backends=backends, action_type=CANCEL_ACTION)

#     def pg_stat_statements_reset(self):
#         sql = """
# -- RESET STATISTICS
# select public.pg_stat_statements_reset();
# """
#         LOG.info(self._prep_log_message("Clearing pg_stat_statements"))
#         self._execute(sql, None)

#         return [{"pg_stat_statements_reset": True}]
