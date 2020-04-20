#! /usr/bin/env python3
#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""
Set the PostgreSQL autovacuum_vacuum_scale_factor parameter on a table-by-table
basis based on the number of tuples in the table.
"""
import logging
import sys
from decimal import Decimal

from psycopg2.extras import NamedTupleCursor


logging.basicConfig(level=logging.INFO, style="{", format="{asctime} {levelname} {message}")

LOG = logging.getLogger()


def reset_table_autovacuum_scale(conn, schema_name, table_name):
    """
    Reset the autovacuum_vacuum_scale_factor parameter on the specified
    table in the specified schema

    Args:
        conn (object): base database connection
        schema_name (str): name of the database schema containing the table
        table_name (str): name of the table

    Returns:
        None
    """
    LOG.info(f"Reset {schema_name}.{table_name} autovacuum_vacuum_scale_factor setting to default")
    sql = f"""
ALTER TABLE {schema_name}.{table_name} reset (autovacuum_vacuum_scale_factor);
"""
    with conn.cursor() as cur:
        cur.execute(sql)


def alter_table_autovacuum_scale(conn, schema_name, table_name, scale_factor):
    """
    Set the autovacuum_vacuum_scale_factor parameter on the specified
    table in the specified schema to the specified value

    Args:
        conn (object): base database connection
        schema_name (str): name of the database schema containing the table
        table_name (str): name of the table
        scale_factor (str/Decimal): the scale factor to which the table parameter should be set

    Returns:
        None
    """
    LOG.info(f"Set {schema_name}.{table_name} autovacuum_vacuum_scale_factor to {scale_factor}")
    sql = f"""
ALTER TABLE {schema_name}.{table_name} set (autovacuum_vacuum_scale_factor = %s);
"""
    with conn.cursor() as cur:
        cur.execute(sql, [scale_factor])


def set_autovacuum_scale_factor(conn):
    """
    Get all analyzed tables in descending order of live tuples.
    Set the scale factor accordingly.

    Args:
        conn (object): base database connection

    Returns:
        None
    """
    sql = """
SELECT s.schemaname,
       s.relname,
       s.n_live_tup,
       s.n_dead_tup,
       case when s.n_live_tup = 0
            then 100.00::numeric(20,2)
            else (s.n_dead_tup::numeric(20,2) / s.n_live_tup::numeric(20,2) * 100.0::numeric(20,2))::numeric(20,2)
       end::numeric(20,2) "dead%",
       s.last_autovacuum,
       s.last_autoanalyze,
       coalesce(table_options.options, '{}'::jsonb) as "options"
  FROM pg_stat_user_tables s
  LEFT
  JOIN (
         select oid,
                jsonb_object_agg(split_part(option, '=', 1), split_part(option, '=', 2)) as options
           from (
                  select oid,
                         unnest(reloptions) as "option"
                    from pg_class
                   where reloptions is not null
                ) table_options_raw
          where option ~ '^autovacuum_vacuum_scale_factor'
          group
             by oid
       ) as table_options
    ON table_options.oid = s.relid
 ORDER
    BY s.n_live_tup desc;
"""

    alter_count = 0
    v_over_10_million_scale = Decimal("0.01")
    v_over_1_million_scale = Decimal("0.02")
    v_over_100_thousand_scale = Decimal("0.05")

    with conn.cursor(cursor_factory=NamedTupleCursor) as cur:
        cur.execute(sql)
        res = cur.fetchall()
        rowcount = cur.rowcount

    for rec in res:
        if rec.n_live_tup >= 10000000:
            if Decimal(rec.options.get("autovacuum_vacuum_scale_factor", 0.0)) < v_over_10_million_scale:
                alter_count += 1
                alter_table_autovacuum_scale(conn, rec.schemaname, rec.relname, v_over_10_million_scale)
        elif rec.n_live_tup >= 1000000:
            if Decimal(rec.options.get("autovacuum_vacuum_scale_factor", 0.0)) < v_over_1_million_scale:
                alter_count += 1
                alter_table_autovacuum_scale(conn, rec.schemaname, rec.relname, v_over_1_million_scale)
        elif rec.n_live_tup >= 100000:
            if Decimal(rec.options.get("autovacuum_vacuum_scale_factor", 0.0)) < v_over_100_thousand_scale:
                alter_count += 1
                alter_table_autovacuum_scale(conn, rec.schemaname, rec.relname, v_over_100_thousand_scale)
        else:
            # Reset to defalt any previously-set table autovacuum_vacuum_scale_factor
            # if live tuples < 100000
            if "autovacuum_vacuum_scale_factor" in rec.options:
                alter_count += 1
                reset_table_autovacuum_scale(conn, rec.schemaname, rec.relname)

    LOG.info(f"Altered {alter_count}/{rowcount} tables ({round(float(alter_count)/float(rowcount) * 100.0, 2)}%)")


def django_set_autovacuum_scale_factor(conn):
    """
    Helper to execute the set_autovacuum_scale_factor from a django migration

    Args:
        conn (DatabaseWrapper): django.db.connection (the default database connection)

    Returns:
        None
    """
    set_autovacuum_scale_factor(conn.connection)


if __name__ == "__main__":
    """
    Allow this functionality to be called via the command line.
    """
    import psycopg2

    with psycopg2.connect(sys.argv[1], cursor_factory=NamedTupleCursor) as conn:
        LOG.info("Connected to {dbname} at {host} on {port} as {user}".format(**conn.get_dsn_parameters()))
        try:
            set_autovacuum_scale_factor(conn)
        except Exception as e:
            LOG.error(e)
            conn.rollback()
        else:
            conn.commit()
