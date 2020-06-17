#!/usr/bin/env python3
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
This program will convert source tables with data into partitioned tables,
copying the data from source to the new partitioned table. All required
table partitions to hold the data will also be created as well as a default
partition.
"""
import argparse
import datetime
import decimal
import json
import logging
import os
import re
import sys
from collections import defaultdict
from collections import namedtuple

import psycopg2
import sqlparse
import yaml
from dateutil import relativedelta
from psycopg2.extras import Json
from psycopg2.extras import NamedTupleCursor
from pytz import UTC


INDEX_PARSER = re.compile("(^.+INDEX )(.+)( ON )(.+)( USING.+$)", flags=re.IGNORECASE)
SQL_SCRIPT_FILE = None
TABLE_CACHE = {}

logging.basicConfig(level=logging.INFO, style="{", format="{filename}:{asctime}:{levelname}:{message}")

LOG = logging.getLogger(os.path.basename(sys.argv[0]))
LINFO = LOG.info
LERROR = LOG.error
LWARN = LOG.warning
LDEBUG = LOG.debug


class RecAttrs:
    pass


def db_json_dumps(d):
    """
    Dump json data using str as the default transform
    Args:
        d (dict) : data
    Returns:
        str : json-formatted string form of d
    """
    return json.dumps(d, default=str)


def json_adapter(d):
    """
    Set the psycopg2 Json class for dict data using db_json_dumps as the dump function
    Args:
        d (dict) : data
    Returns:
        Json : data (d) in a Json instance so that the psycopg2 driver can process it
    """
    return Json(d, dumps=db_json_dumps)


def generate_sample_config():
    cfg = {
        "partition_targets": {
            "<schema>": [
                {
                    "<table_name>": {
                        "target_schema": "<schema_name>, # Optional. If not found, then "
                        "target_schema = processing schema",
                        "partition_key": "<column_name>",
                        "partition_type": '<partition-type>, # should be "list" or "range"',
                        "<partition-type>": {
                            "values": "[[<values here>], ...], # List of lists. Required for " "list partition type",
                            "interval_type": '<val>     # If date, timestamp type, choose "month" '
                            'or "year". If numeric type, choose the appropriate DB '
                            "data type (int, numeric(10,2), etc). Required for "
                            "range partition type",
                            "interval": "<val>          # The interval itself: 1, 5, 10, etc. "
                            "Required for range partition type",
                        },
                        "primary_key": {
                            "<column_name>": {
                                "data_type": "# data type of the column",
                                "default": "# A default value, if any. To omit, set to null or empty string",
                                "copy_sequence": "# Copy the source table column's sequence to the new table's "
                                "column, set to 1 else set to 0",
                                "new_sequence": {
                                    "sequence_name": "# Name of the sequence",
                                    "table_name": "# Name of the table",
                                    "column_name": "# Name of the column in the table that will be the owner",
                                    "start_value": "# Sequence starting value",
                                    "min_value": "# Minimum value",
                                    "max_value": "# Maximum value",
                                    "cache_size": "# Number of values to cache (>= 1)",
                                    "cycle": "# 1 = Cycle; 0 = No Cycle",
                                },
                            }
                        },
                        "triggers": [
                            {
                                "name": '# name of the trigger, you can use "{table_name}" as a '
                                "placeholder for the name of the table",
                                "when": "# BEFORE | AFTER",
                                "action": "# INSERT | UPDATE | DELETE",
                                "columns": "# List [] of columns to constrain the trigger",
                                "function": "# Function to execute. Include the schema name if outside "
                                "of processing schema",
                            }
                        ],
                        "drop_source_table": "boolean          # Drop the source table after data migration. "
                        "False by default",
                        "copy_column_map": {"<insert_col_name>": "<source_column_name_or_expression>"},
                    }
                }
            ],
            "*": [
                {
                    "<table_name>": {
                        "target_schema": "<schema_name>, # Optional. If not found, then "
                        "target_schema = processing schema",
                        "partition_key": "<column_name>",
                        "partition_type": '<partition-type>, # should be "list" or "range"',
                        "<partition-type>": {
                            "values": "[[<values here>], ...], # List of lists. Required for " "list partition type",
                            "interval_type": '<val>     # If date, timestamp type, choose "month" '
                            'or "year". If numeric type, choose the appropriate DB '
                            "data type (int, numeric(10,2), etc). Required for "
                            "range partition type",
                            "interval": "<val>          # The interval itself: 1, 5, 10, etc. "
                            "Required for range partition type",
                        },
                        "primary_key": {
                            "<column_name>": {
                                "data_type": "# data type of the column",
                                "default": "# A default value, if any. To omit, set to null or empty string",
                                "copy_sequence": "# Copy the source table column's sequence to the new table's "
                                "column, set to 1 else set to 0",
                                "new_sequence": {
                                    "sequence_name": "# Name of the sequence",
                                    "table_name": "# Name of the table",
                                    "column_name": "# Name of the column in the table that will be the owner",
                                    "start_value": "# Sequence starting value",
                                    "min_value": "# Minimum value",
                                    "max_value": "# Maximum value",
                                    "cache_size": "# Number of values to cache (>= 1)",
                                    "cycle": "# 1 = Cycle; 0 = No Cycle",
                                },
                            }
                        },
                        "triggers": [
                            {
                                "name": '# name of the trigger, you can use "{table_name}" as a '
                                "placeholder for the name of the table",
                                "when": "# BEFORE | AFTER",
                                "action": "# INSERT | UPDATE | DELETE",
                                "columns": "# List [] of columns to constrain the trigger",
                                "function": "# Function to execute. Include the schema name if outside "
                                "of processing schema",
                            }
                        ],
                        "drop_source_table": "boolean          # Drop the source table after data migration. "
                        "False by default",
                        "copy_column_map": {"<insert_col_name>": "<source_column_name_or_expression>"},
                    }
                }
            ],
        },
        "stored_procedures": {
            "<schema_name>": {
                "depends_on_schema": "# put a required schema here to process it first. Omit this key if not needed",
                "code": ["Put any sql code for stored procedures/functions here"],
            },
            "*": {
                "depends_on_schema": "# put a required schema here to process it first. Omit this key if not needed",
                "code": ["Put any sql code for stored procedures/functions here"],
            },
        },
    }
    comment_buff = """
#
# The "*" schema matches any schema not explicitly listed as a partition target or stored procedure schema
#
# The "<partiiton-type>" value **must** match the value from the "partition_type" key
#
# To simply list existing columns with no changes for a new partition key, then set the column_name as the
# key with an empty set of attributes
#
# Omit or have an empty set of attributes for new_sequence to not create a new sequence
#
# Omit or have an empty set of attributes for triggers to suppress any trigger creation
#
"""
    yaml.safe_dump(cfg, sys.stdout, sort_keys=True, width=255)
    print(comment_buff, flush=True)


def load_config(config_file_name):
    """
    Load the config file. This is a YAML file.
    Args:
        config_file_name (str) : path to the config file
    Returns:
        dict : The config as read from the YAML
    """
    return yaml.safe_load(open(config_file_name, "rt"))


def connect(db_url):
    """
    Connect to the database
    Args:
        db_url (str) : DB connect string as a URL
    Returns:
        datbase connection class instance
    """
    conn = psycopg2.connect(db_url, cursor_factory=NamedTupleCursor, application_name=os.path.basename(sys.argv[0]))
    LINFO("Connected to {dbname} on {host} at port {port} as user {user}".format(**conn.get_dsn_parameters()))

    return conn


def mogrify_sql(cur, sql, values=None):
    """
    Returns a formatted SQL string from the SQL and arguments
    Args:
        cur (Cursor) : cursor to process the SQL
        sql (str) : The SQL string
        values (list, dict, None) : The values (if any) for the SQL statements. Default = None
    Returns:
        str : The formatted SQL with parameters
    """
    try:
        mog_sql = sqlparse.format(
            cur.mogrify(sql, values), encoding="utf-8", reindent_aligned=True, keyword_case="upper"
        )
    except psycopg2.ProgrammingError:
        mog_sql = f"""{sqlparse.format(sql, encoding='utf-8', reindent_aligned=True, keyword_case='upper')}
VALUES: {str(values)}"""

    return mog_sql


def execute(conn, sql, values=None, override=False):
    """
    Executes the given SQL against the given database connections
    Args:
        conn (Connection) : Database connection
        sql (str) : SQL string
        values (list, dict, None) : Parameters (if any) for the SQL. Default = None
    Returns:
        Cursor : The cursor instance after statement execution
    """
    cur = conn.cursor()
    sqlbuff = mogrify_sql(cur, sql, values)
    LDEBUG(f"Executiong SQL: {os.linesep}{sqlbuff}")

    sqlexec = override or (not SQL_SCRIPT_FILE)
    if sqlexec:
        cur.execute(sql, values)
    else:
        print(sqlbuff, file=SQL_SCRIPT_FILE, end=os.linesep * 2)

    return cur


def get_table_info(conn, schema_name, table_names):
    """
    Get schema name, table name, column name, column data type, column default value
    for a given list of tables. Columns will be in defined column order.
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Name of schema in which table(s) should reside
        table_names (str, list) : comma-separated string of table names or a list of table names
    Returns:
        dict : Returned table info indexed by table_name
    """
    if not (bool(schema_name) or bool(table_names)):
        return {}

    sql = """
select n.nspname as "schema_name",
       c.relname as "table_name",
       a.attname as "column_name",
       format_type(a.atttypid, a.atttypmod) as "data_type",
       a.attnotnull as "not_null",
       (SELECT substring(pg_catalog.pg_get_expr(d.adbin, d.adrelid) for 128)
          FROM pg_catalog.pg_attrdef d
         WHERE d.adrelid = a.attrelid
           AND d.adnum = a.attnum
           AND a.atthasdef) as "default"
  from pg_class c
  join pg_namespace n
    on n.oid = c.relnamespace
  join pg_attribute a
    on a.attrelid = c.oid
   and a.attnum > 0
   and not a.attisdropped
 where n.nspname = %(schema)s
   and c.relkind = 'r'
   and c.relname = any( %(tables)s )
 order by c.relname,
          a.attnum;
"""
    if isinstance(table_names, str):
        v_table_names = [t.strip() for t in table_names.split(",")]
    else:
        v_table_names = list(table_names)

    LINFO(f"Getting info for table(s): {', '.join(v_table_names)}")
    values = {"schema": schema_name, "tables": v_table_names}
    res = defaultdict(list)
    for rec in execute(conn, sql, values, override=True):
        res[rec.table_name].append(rec)

    return res


def get_table_indexes(conn, schema_name, table_names):
    """
    Get index information for table(s) in a specified schema
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Name of schema in which table(s) should reside
        table_names (str, list) : comma-separated string of table names or a list of table names
    Returns:
        dict : Returned index info indexed by table_name
    """
    sql = """
with pk_indexes as (
select i.relname
  from pg_class t
  join pg_namespace n
    on n.oid = t.relnamespace
  join pg_index x
    on x.indrelid = t.oid
   and x.indisprimary = true
  join pg_class i
    on i.oid = x.indexrelid
 where n.nspname = %(schema)s
   and t.relname = any( %(tables)s )
   and t.relkind = 'r'
)
select i.*
  from pg_indexes i
 where i.schemaname = %(schema)s
   and i.tablename = any( %(tables)s )
   and not exists (select 1 from pk_indexes x where i.indexname = x.relname)
 order
    by i.tablename;
"""
    if isinstance(table_names, str):
        v_table_names = [t.strip() for t in table_names.split(",")]
    else:
        v_table_names = list(table_names)

    LINFO(f"Getting indexes for table(s): {', '.join(v_table_names)}")
    values = {"schema": schema_name, "tables": v_table_names}
    res = defaultdict(list)
    for rec in execute(conn, sql, values, override=True):
        res[rec.tablename].append(rec)

    return res


def get_table_constraints(conn, schema_name, table_names):
    """
    Get constraint information for table(s) in a specified schema
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Name of schema in which table(s) should reside
        table_names (str, list) : comma-separated string of table names or a list of table names
    Returns:
        dict : Returned constraint info indexed by table_name
    """
    sql = """
select c.oid::int as constraint_oid,
       n.nspname::text as schema_name,
       t.relname::text as table_name,
       c.conname::text as constraint_name,
       c.contype::text as constraint_type,
       c.condeferrable as is_deferrable,
       c.condeferred as is_deferred,
       (select array_agg(tc.attname::text)
          from pg_attribute tc
         where tc.attrelid = c.conrelid
           and tc.attnum = any(c.conkey)) as constraint_columns,
       f.relname::text as reference_table,
       c.confupdtype as update_action,
       c.confdeltype as delete_action,
       (select array_agg(fc.attname::text)
          from pg_attribute fc
         where fc.attrelid = c.confrelid
           and fc.attnum = any(c.confkey)) as reference_columns,
       pg_get_constraintdef(c.oid, true) as "definition"
  from pg_constraint c
  join pg_class t
    on t.oid = c.conrelid
   and t.relkind = 'r'
  join pg_namespace n
    on n.oid = t.relnamespace
  left
  join pg_class f
    on f.oid = c.confrelid
   and f.relkind = 'r'
 where c.conrelid > 0
   and n.nspname = %(schema)s
   and t.relname = any( %(tables)s )
 order
    by t.relname,
       case when c.contype = 'p'
                 then 0
            else 1
       end::int
"""
    if isinstance(table_names, str):
        v_table_names = [t.strip() for t in table_names.split(",")]
    else:
        v_table_names = list(table_names)

    LINFO(f"Getting constraints for table(s): {', '.join(v_table_names)}")
    values = {"schema": schema_name, "tables": v_table_names}
    res = defaultdict(list)
    for rec in execute(conn, sql, values, override=True):
        res[rec.table_name].append(rec)

    return res


def get_table_views(conn, schema_name, table_names):
    """
    Get view information for table(s) in a specified schema
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Name of schema in which table(s) should reside
        table_names (str, list) : comma-separated string of table names or a list of table names
    Returns:
        dict : Returned view info indexed by table_name
    """
    sql = """
select m.schemaname,
       t.table_name,
       m.matviewname as view_name,
       'matview'::text as view_type,
       m.definition,
       coalesce((select jsonb_object_agg(i.indexname::text, i.indexdef::text)
                   from pg_indexes i
                  where i.schemaname = m.schemaname
                    and i.tablename = m.matviewname), '{}'::jsonb) as indexes
  from pg_matviews m
  join unnest( %(tables)s ) as t(table_name)
    on m.definition ~ t.table_name
 where m.schemaname = %(schema)s
 union
select v.schemaname,
       t.table_name,
       v.viewname as view_name,
       'view' as view_type,
       v.definition,
       '{}'::jsonb as indexes
  from pg_views v
  join unnest( %(tables)s ) as t(table_name)
    on v.definition ~ t.table_name
 where v.schemaname = %(schema)s
 order
    by table_name;
"""
    if isinstance(table_names, str):
        v_table_names = [t.strip() for t in table_names.split(",")]
    else:
        v_table_names = list(table_names)

    LINFO(f"Getting views referencing table(s): {', '.join(v_table_names)}")
    values = {"schema": schema_name, "tables": v_table_names}
    res = defaultdict(list)
    for rec in execute(conn, sql, values, override=True):
        res[rec.table_name].append(rec)

    return res


def get_table_sequences(conn, schema_name, table_names):
    """
    Get sequence information for table(s) in a specified schema
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Name of schema in which table(s) should reside
        table_names (str, list) : comma-separated string of table names or a list of table names
    Returns:
        dict : Returned sequence info indexed by table_name
    """
    sql = """
select t.relname::text as table_name,
       a.attname::text as column_name,
       seq.*
  from pg_class t
  join pg_depend d
    on d.refobjid = t.oid
  join pg_class s
    on s.oid = d.objid
   and s.relkind = 'S'
  join pg_attribute a
    on a.attrelid = d.refobjid
   and a.attnum = d.refobjsubid
   and a.attnum > 0
  join pg_namespace ts
    on ts.oid = t.relnamespace
  join pg_namespace ss
    on ss.oid = s.relnamespace
  join pg_sequences seq
    on seq.schemaname = ss.nspname
   and seq.sequencename = s.relname
 where ts.nspname = %(schema)s
   and t.relname = any( %(tables)s )
   and d.classid = 'pg_class'::regclass;
"""
    if isinstance(table_names, str):
        v_table_names = [t.strip() for t in table_names.split(",")]
    else:
        v_table_names = list(table_names)

    LINFO(f"Getting sequences for table(s): {', '.join(v_table_names)}")
    values = {"schema": schema_name, "tables": v_table_names}
    res = defaultdict(list)
    for rec in execute(conn, sql, values, override=True):
        res[rec.table_name].append(rec)

    return res


def db_schemas(conn):
    """
    Generator   that returns all user schemata
    Args:
        conn (Connection) : Database connection
    Returns:
        (generator returning str) : schema name
    """
    sql = """
select distinct
       schemaname
  from pg_stat_user_tables
 where schemaname !~ '^pg_temp'
 order
    by schemaname;
    """
    for rec in execute(conn, sql, override=True).fetchall():
        LINFO(f"Processing schema {rec.schemaname}")
        yield rec.schemaname


def get_partition_targets(conf, schema):
    """
    Return the partition targets for the specified schema or for "*"
    Args:
        conf (dict): Configuration
        schema (str): Schema name
    Returns:
        dict: table partition info for all target tables
    """
    all_targets = conf["partition_targets"]
    schema_targets = all_targets.get(schema, all_targets.get("*", {}))

    return schema_targets


def partition_table_targets(conn, schema, conf):
    """
    Return table info for partition targets from config file
    Args:
        conn (Connection) : Database connection
        schema (str) : Schema name
        conf (dict) : Program config settings
    Returns:
        generator returning dict : {'structure': [<table_info_column_rec>],
                                    'partition_info': config partition settings for table}
    """
    schema_targets = get_partition_targets(conf, schema)
    fetch_targets = set(schema_targets) - set(TABLE_CACHE)
    if fetch_targets:
        LINFO(f"Caching table info for {','.join(fetch_targets)}")
        ixinfo = get_table_indexes(conn, schema, fetch_targets)
        cnstinfo = get_table_constraints(conn, schema, fetch_targets)
        viewinfo = get_table_views(conn, schema, fetch_targets)
        seqinfo = get_table_sequences(conn, schema, fetch_targets)
        TABLE_CACHE.update(
            {
                k: {
                    "structure": v,
                    "indexes": ixinfo.get(k, []),
                    "constraints": cnstinfo.get(k, []),
                    "views": viewinfo.get(k, []),
                    "sequences": seqinfo.get(k, []),
                    "partition_info": schema_targets[k],
                }
                for k, v in get_table_info(conn, schema, fetch_targets).items()
            }
        )
    else:
        LINFO("All table targets cached")

    for table_name in schema_targets:
        LINFO(f"Processing table {table_name}")
        yield TABLE_CACHE[table_name]


def get_partition_key_bounds(conn, schema_name, table_info):
    """
    Using partition information, get the lower and upper bounds of the
    partiton key value for the table partition definition
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Schema name
        table_info (dict) : Table definition and Partition definition
    Returns:
        tuple : (lower_key_value, upper_key_value)
    """
    partition_key = table_info["partition_info"]["partition_key"]
    partition_key_type = get_partition_key_data_type(table_info)
    table_name = table_info["structure"][0].table_name
    sql = f"""
select min({partition_key}) as min_partition_value,
       max({partition_key}) as max_partition_value
  from {schema_name}.{table_name};
"""
    ResultRow = namedtuple("ResultRow", ["min_partition_value", "max_partition_value"])
    LINFO(f"Getting min and max values for {schema_name}.{table_name}.{partition_key}")
    res = execute(conn, sql, override=True).fetchone()

    if res.min_partition_value is None and partition_key_type in (
        "date",
        "timestamp with time zone",
        "timestamp without time zone",
        "timestamp",
        "timestamptz",
    ):
        val = (datetime.date.today() - relativedelta.relativedelta(months=6)).replace(day=1)
        if partition_key_type.startswith("time"):
            val = datetime.datetime(*val.timetuple()[:3]).replace(tzinfo=UTC)
        res = ResultRow(min_partition_value=val, max_partition_value=res.max_partition_value)

    if res.max_partition_value is None and partition_key_type in (
        "date",
        "timestamp with time zone",
        "timestamp without time zone",
        "timestamp",
        "timestamptz",
    ):
        val = (datetime.date.today() + relativedelta.relativedelta(months=6)).replace(day=1)
        if partition_key_type.startswith("time"):
            val = datetime.datetime(*val.timetuple()[:3]).replace(tzinfo=UTC)
        res = ResultRow(min_partition_value=res.min_partition_value, max_partition_value=val)

    return (res.min_partition_value, res.max_partition_value)


def get_partition_key_data_type(table_info):
    """
    Get the DB data type of the partition key
    Args:
        table_info (dict) : Table definition and Partition definition
    Returns:
        str : data type spec
    """
    partition_key = table_info["partition_info"]["partition_key"]
    for col_info in table_info["structure"]:
        if col_info.column_name == partition_key:
            return col_info.data_type


def floor_date(date_val, scale):
    """
    Returns the appropriate day 1 value for a month scale or year scale
    Args:
        date_val (datetime, date) : Date value
        scale (str) : Should be "month" or "year"
    Returns:
        date : the day 1 date value
        None : error
    """
    if isinstance(date_val, datetime.datetime):
        date_val = datetime.date()

    if scale == "month":
        return date_val.replace(day=1)
    elif scale == "year":
        return date_val.replace(month=1, day=1)


def ceil_date(date_val, scale):
    """
    Find the max exclusive date value for the scale of month or year.
    Args:
        date_val (datetime, date) : Date value
        scale (str) : Should be "month" or "year"
    Returns:
        date : the day 1 date value of the next scale period
        None : error
    """
    if isinstance(date_val, datetime.datetime):
        date_val = datetime.date()

    if scale == "month":
        return (date_val + relativedelta.relativedelta(months=1)).replace(day=1)
    elif scale == "year":
        return datetime.date(date_val.year + 1, 1, 1)


def resolve_partition_key_minimum(table_info, min_val):
    """
    Resolve the minimum value for the parititon type and values
    Args:
        table_info (dict) : structure definition and partition definition
        min_val (datetime, date, int, str) : min_val used in the resolution
    Returns:
        Resolve value of the same min_val type
    """
    partition_type = table_info["partition_info"]["partition_type"]
    partition_type_info = table_info["partition_info"][partition_type]
    if partition_type == "range":
        if isinstance(min_val, (datetime.datetime, datetime.date)):
            return floor_date(min_val, partition_type_info["interval_type"])
        else:
            return min_val
    else:
        raise ValueError(
            f"Invalid partition type '{partition_type}'. Partition type should be either 'list' or 'range'"
        )


def resolve_partition_key_maximum(table_info, max_val):
    """
    Resolve the maximum value for the parititon type and values
    Args:
        table_info (dict) : structure definition and partition definition
        max_val (datetime, date, int, str) : max_val used in the resolution
    Returns:
        Resolve value of the same max_val type
    """
    partition_type = table_info["partition_info"]["partition_type"]
    partition_type_info = table_info["partition_info"][partition_type]
    if partition_type == "range":
        if isinstance(max_val, (datetime.datetime, datetime.date)):
            return ceil_date(max_val, partition_type_info["interval_type"])
        elif isinstance(max_val, decimal.Decimal):
            return max_val + decimal.Decimal("1")
        else:
            return max_val + 1
    else:
        raise ValueError(
            f"Invalid partition type '{partition_type}'. Partition type should be either 'list' or 'range'"
        )


def create_partition_table_tracker(conn, schema_name):
    """
    Create a table that will hold the partitions created by
    this program and the definitions of those partitions
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Schema into which this table will be created
    Returns:
        None
    """
    execute(conn, f"drop table if exists {schema_name}.partitioned_tables;")
    sql = f"""
create table if not exists {schema_name}.partitioned_tables
(
    schema_name text not null default '{schema_name}',
    table_name text not null,
    partition_of_table_name text not null,
    partition_type text not null,
    partition_col text not null,
    partition_parameters jsonb not null,
    constraint table_partition_pkey primary key (schema_name, table_name)
);
"""
    execute(conn, sql)

    sql = f"""
create index "partable_table" on {schema_name}.partitioned_tables (table_name, schema_name);
"""
    execute(conn, sql)

    sql = f"""
create index "partable_partition_parameters" on {schema_name}.partitioned_tables using GIN (partition_parameters);
"""
    execute(conn, sql)

    sql = f"""
create index "partable_partition_type" on {schema_name}.partitioned_tables (partition_type);
"""
    execute(conn, sql)


def add_partition_track_record(conn, partition_table_record):
    """
    Add a record to the partition tracking table
    Args:
        conn (Connection) : Database connection
        partition_table_record (dict) : Record data
    """
    sql = f"""
insert into {partition_table_record['schema_name']}.partitioned_tables
(
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters
)
values
(
    %(schema_name)s,
    %(table_name)s,
    %(partition_of_table_name)s,
    %(partition_type)s,
    %(partition_col)s,
    %(partition_parameters)s
);
"""
    LINFO(
        f"Creating partiton tracking record for {partition_table_record['schema_name']}"
        f".{partition_table_record['table_name']}"
    )
    execute(conn, sql, partition_table_record)


def partition_table(conn, schema_name, table_info):
    """
    Create a new partitioned table from the original table definition.
    This will create a new structure that will consist of the partitioned table
    as well as the required number of table partitions that will hold the
    original table's data.
    Args:
        conn (Connection) : Database connection
        schema_name (str) : schema in which the source table resides
        table_info (dict) : Table structure and partition settings
    Returns:
        None
    """
    partition_type = table_info["partition_info"]["partition_type"]
    if partition_type == "range":
        min_val, max_val = get_partition_key_bounds(conn, schema_name, table_info)
        partition_min = resolve_partition_key_minimum(table_info, min_val)
        partition_max = resolve_partition_key_maximum(table_info, max_val)
        partition_values = [partition_min, partition_max]
    else:
        partition_values = table_info["partition_info"][partition_type]["values"]

    create_partitioned_table(conn, schema_name, table_info, partition_values)


def build_partitioned_table_sql(schema_name, table_info):
    """
    Generate the CREATE TABLE statement for the partitioned table
    Args:
        schema_name (str) : Schema name into which this table should be created
        table_info (dict) : Table structure and partition information
    Returns:
        str : CREATE TABLE statement
    """
    table_name = table_info["structure"][0].table_name
    seq_cols = {s.column_name for s in table_info["sequences"]}
    sql = [f"create table if not exists {schema_name}.p_{table_name}", "("]
    sqlcols = []
    for i in table_info["structure"]:
        colspec = {
            "column_name": i.column_name,
            "data_type": i.data_type,
            "not_null": "not null" if i.not_null else "",
            "default": "" if i.column_name in seq_cols or not i.default else i.default,
        }
        coldef = "    {column_name} {data_type} {not_null} {default}".format(**colspec)
        sqlcols.append(coldef)

    sql.append(f",{os.linesep}".join(sqlcols))
    sql.extend([")", ""])

    return os.linesep.join(sql)


def range_interval_gen(interval_type, interval, partition_values):
    """
    Generator that yields a tuple of the min and max values
    for a date range table partition.
    Args:
        interval_type (str) : Interval type for the partition. Should be "month" or "year"
        interval (int) : Interval
        partition_values (list) : (start_val, end_val)
    Returns:
        tuple : A start, end pair within the partition values bounds by the interval type and interval
    """
    interval = int(interval)
    if interval_type == "month":
        reldel_params = {"months": interval}
    elif interval_type == "year":
        reldel_params = {"years": interval}
    else:
        raise ValueError(f"Invalid value {interval_type} for interval_type")

    reldel = relativedelta.relativedelta(**reldel_params)
    start = end = partition_values[0]
    # This should generate one extra range, which will probably be a good thing in this case.
    while start < partition_values[1]:
        start = end
        end = (start + reldel).replace(day=1)
        if isinstance(start, datetime.datetime):
            start = datetime.datetime(*start.timetuple()[:3]).replace(tzinfo=UTC)
            end = datetime.datetime(*end.timetuple()[:3]).replace(tzinfo=UTC)

        yield (start, end)


def get_primary_key_ix(table_info):
    """
    Return the list index of the primary key constraint information from the table constraints
    Args:
        table_info (dict): table_info (structure, constraints, partition_info, etc)
    Returns:
        int: >= 0 is valid index
             < 0 is not found
    """
    for i, c_spec in enumerate(table_info["constraints"]):
        if c_spec.constraint_type == "p":
            return i

    return -1


def find_column_index(table_info, column_name):
    """
    Return the list index of the column definition
    Args:
        table_info (dict): table_info (structure, constraints, partition_info, etc)
    Returns:
        int: >= 0 is valid index
             < 0 is not found
    """
    structure = table_info["structure"]
    for i, coldef in enumerate(structure):
        if coldef.column_name == column_name:
            return i

    return -1


def add_new_sequence(table_info, sequence_spec):
    """
    Add a new sequence record to the table_info
    Args:
        table_info (dict): The table information as read from the database
        sequence_spec (dict): All information needed to process a sequence
    Returns:
        None
    """
    new_sequence = RecAttrs()
    for key, val in sequence_spec.items():
        setattr(new_sequence, key, val)
    table_info["sequences"].insert(0, new_sequence)


def process_table_primary_key(table_info):
    """
    Process a primary key element defined in the config (if any)
    This will either redefine a primary key from existing columns or add new columns.
    Existing columns can have certain attributes redefined by the config driving this
    function as well.
    Args:
        table_info (dict): Table information read from the database and its partition info from the config
    Returns:
        None
    """
    pk_info = table_info["partition_info"].get("primary_key")
    if pk_info:
        pk_ix = get_primary_key_ix(table_info)
        if pk_ix >= 0:
            table_name = table_info["structure"][0].table_name
            new_pk_spec = RecAttrs()
            setattr(new_pk_spec, "constraint_type", "p")
            setattr(new_pk_spec, "constraint_name", table_info["constraints"][pk_ix].constraint_name)
            new_constraint_cols = []
            for col_name, col_spec in pk_info.items():
                new_seq_spec = col_spec.get("new_sequence")
                if new_seq_spec:
                    add_new_sequence(table_info, new_seq_spec)

                new_constraint_cols.append(col_name)

                orig_col_ix = find_column_index(table_info, col_name)
                orig_col = table_info["structure"][orig_col_ix] if orig_col_ix >= 0 else RecAttrs()
                new_col = RecAttrs()
                setattr(new_col, "table_name", table_name)
                setattr(new_col, "column_name", col_name)
                setattr(new_col, "data_type", col_spec.get("data_type", orig_col.data_type))
                setattr(new_col, "not_null", False)
                setattr(new_col, "default", col_spec.get("default", orig_col.default))

                if orig_col_ix >= 0:
                    table_info["structure"][orig_col_ix] = new_col
                else:
                    table_info["structure"].insert(0, new_col)

            setattr(new_pk_spec, "constraint_columns", new_constraint_cols)
            table_info["constraints"][pk_ix] = new_pk_spec


def create_table_triggers(conn, schema_name, table_info):
    """
    Create triggers for the table based on the partition configuration
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_info (dict): Table information from the database and table partition configuration
    Returns:
        None
    """
    table_name = table_info["structure"][0].table_name
    trigger_info = table_info["partition_info"].get("triggers")
    if trigger_info:
        LINFO(f"Creating triggers on table {schema_name}.{table_name}")
        for trigger in trigger_info:
            trigger_name = trigger["name"].format(table_name=table_name)
            trigger_sql = [f"create trigger {trigger_name} {trigger['when']} {trigger['action']} "]
            cols = trigger.get("columns")
            if cols:
                trigger_sql.append(f"of {', '.join(cols)}")
            trigger_sql.append(f"on {schema_name}.{table_name}")
            func = trigger["function"].format(schema_name=schema_name)
            if not func.endswith("()"):
                func += "()"
            trigger_sql.append(f"for each row execute function {func} ;")

            execute(conn, os.linesep.join(trigger_sql))
    else:
        LINFO(f"No triggers to create on table {schema_name}.{table_name}")


def create_table_sequences(conn, schema_name, table_name, table_info):
    """
    Create all sequences on the target partitioned table from the source table providing
    that the sequence for the column is not blocked by the configuration primary key column
    setting.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Target table name
        table_info (dict): Table structure and partition configuration
    Returns:
        None
    """
    LINFO(f"Creating sequences for table {schema_name}.{table_name}")
    sequence_info = table_info["sequences"]
    no_seq = {k for k, v in table_info["partition_info"].get("primary_key", {}).items() if not v.get("copy_sequence")}
    for s_spec in sequence_info:
        if s_spec.column_name in no_seq:
            continue

        sql = f"""
create sequence {schema_name}.{s_spec.sequencename} as {s_spec.data_type}
increment by %(increment_by)s
minvalue %(min_value)s
maxvalue %(max_value)s
start with %(start_value)s
cache %(cache_size)s
{'no ' if not s_spec.cycle else ''}cycle ;
"""
        values = {
            "increment_by": s_spec.increment_by,
            "min_value": s_spec.min_value,
            "max_value": s_spec.max_value,
            "start_value": s_spec.start_value,
            "cache_size": s_spec.cache_size,
        }
        execute(conn, sql, values)

        if s_spec.last_value:
            sql = "select setval(%s::regclass, %s);"
            execute(conn, sql, (f"{schema_name}.{s_spec.sequencename}", s_spec.last_value))

        sql = f"""
alter table {schema_name}.{table_name}
alter column {s_spec.column_name} set default nextval(%(seqname)s::regclass) ;
"""
        execute(conn, sql, {"seqname": f"{schema_name}.{s_spec.sequencename}"})

        sql = f"""
alter sequence {schema_name}.{s_spec.sequencename}
owned by {schema_name}.{table_name}.{s_spec.column_name} ;
"""
        execute(conn, sql)


def create_partitioned_table(conn, schema_name, table_info, partition_values):
    """
    Create the partitioned table from the source table definition. Also create the
    default partition plus any partitions needed based on the data in the table as well
    as the partition settings from the config.
    Note, there will be several commits during this function execution
    Args:
        conn (Connection) : Database connection
        schema_name (str) : Schema of source table
        table_info (dict) : Structure and partition settings of the table to be partitioned
        parttiion_values (list, tuple) : For list partition type, this should be a list of lists of discrete values
                                         For range partition type, this should be a tuple of the lower and upper bounds
    Returns:
        None
    """
    table_name = table_info["structure"][0].table_name
    target_schema = table_info["partition_info"].get("target_schema", schema_name)
    partition_key = table_info["partition_info"]["partition_key"]
    partition_type = table_info["partition_info"]["partition_type"]
    partition_interval_type = table_info["partition_info"][partition_type]["interval_type"]
    partition_interval = table_info["partition_info"][partition_type]["interval"]

    # Rename source sequences
    rename_source_sequences(conn, schema_name, table_name, table_info["sequences"])

    # Handle any primary key redefinition
    process_table_primary_key(table_info)

    # Create the main partitioned table
    sql = f"""{build_partitioned_table_sql(target_schema, table_info)}partition by {partition_type} ({partition_key});
"""
    LINFO(f"Creating partitioned table {target_schema}.p_{table_name}...")
    execute(conn, f"drop table if exists {target_schema}.p_{table_name};")
    execute(conn, sql)

    # Create any sequences
    create_table_sequences(conn, target_schema, "p_" + table_name, table_info)

    # Handle any triggers
    create_table_triggers(conn, target_schema, table_info)

    # Add the constraints.
    create_partitioned_table_constraints(
        conn, target_schema, "p_" + table_name, table_info["constraints"], partition_key
    )

    # Add the indexes.
    create_partitioned_table_indexes(conn, target_schema, "p_" + table_name, table_info["indexes"])

    # Create the default partition
    create_table_partition(conn, target_schema, table_name, "default", (), -1, partition_key)

    # Resolve the range generator for the partitions needed
    if partition_type == "range":
        partitoin_range_generator = range_interval_gen(partition_interval_type, partition_interval, partition_values)
    else:
        partitoin_range_generator = iter(partition_values)

    # Now create the actual partitions
    for range_ix, partition_range in enumerate(partitoin_range_generator):
        create_table_partition(
            conn, target_schema, table_name, partition_type, partition_range, range_ix, partition_key
        )

    # Before renaming the tables, we need to handle references in views
    # Now that the partitioned structures are in place, rename so that the partitioned
    # tables get all of the new inserts.
    # Selects, Updates, and Deletes will fail during the copy.
    # This function will execute a COMMIT
    rename_tables(conn, schema_name, table_name, target_schema, "p_" + table_name, table_info)

    # Now comes the copy of the data.
    copy_data(conn, schema_name, "__" + table_name, target_schema, table_name, table_info)
    conn.commit()

    create_views(conn, target_schema, table_name, table_info["views"])
    refresh_materialized_views(conn, table_info["views"])

    # And drop the old source table if we're told to.
    if table_info["partition_info"].get("drop_table", False):
        drop_table(conn, schema_name, "__" + table_name)
        conn.commit()


def create_partitioned_table_constraints(conn, schema_name, table_name, constraint_info, partition_key):
    """
    Create all constraints on the target partitioned table that are on the source table.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Target table name
        constraint_info (list(NamedTuple)): Table constraint information as read from the database
        partition_key (str): Column name of the partition key
    Returns:
        None
    """
    if constraint_info:
        sqlprefix = f"alter table {schema_name}.{table_name} add constraint {{}} "
        for c_spec in constraint_info:
            sql = sqlprefix.format("p_" + c_spec.constraint_name)
            if c_spec.constraint_type == "p":
                if partition_key not in c_spec.constraint_columns:
                    c_spec.constraint_columns.insert(0, partition_key)
                sql += f'PRIMARY KEY ({", ".join(c_spec.constraint_columns)});'
            else:
                sql += c_spec.definition

            LINFO(f"Creating constraint {c_spec.constraint_name} on table {schema_name}.{table_name}")
            execute(conn, sql)
    else:
        LINFO("No constraints to create")


def create_partitioned_table_indexes(conn, schema_name, table_name, index_info):
    """
    Create indexes on the target partitioned table that exist on the source table.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Target table name
        index_info (list(NamedTuple)): Index info from source table as read from the database
    Returns:
        None
    """
    if index_info:
        index_name_ix = 1
        index_table_ix = -2

        for ixrec in index_info:
            index_parts = INDEX_PARSER.findall(ixrec.indexdef)
            if index_parts:
                index_parts = list(index_parts[0])
                index_parts[index_name_ix] = f"p_{index_parts[index_name_ix]}"
                index_parts[index_table_ix] = f"{schema_name}.{table_name}"
                LINFO(f'Creating index "{index_parts[index_name_ix]}" on table {index_parts[index_table_ix]}')
                execute(conn, "".join(index_parts))
    else:
        LINFO("No indexes to create")


def create_table_partition(conn, target_schema, table_name, partition_type, partition_range, range_ix, partition_col):
    """
    Create a partition of the partitioned table.
    Args:
        conn (Connection) : Database connection
        target_schema (str) : schema in which the partition should be created
        table_name (str) : name of the source table
        partition_type (str) : "list", "range", "default"
        partition_range (tuple) : For list partition, this should be a collection of discrete values
                                  For range partition, this should be a tuple of (low, high) values
                                  where low <= partition_key_value < high
        range_ix (int) : Used for naming list partitions
        partition_col (str) : Used for tracking
    """
    if partition_type == "list":
        partition_suffix = str(range_ix)
        range_clause = "for values in (%s)"
        values = [tuple(partition_range)]
        partition_parameters = {"in": values[0], "default": False}
    elif partition_type == "default":
        partition_suffix = "default"
        partition_parameters = {"default": True}
        range_clause = "DEFAULT"
        values = None
    else:
        range_clause = "for values from (%s) to (%s)"
        values = partition_range
        partition_parameters = {"from": str(partition_range[0]), "to": str(partition_range[1]), "default": False}

        if isinstance(partition_range[0], (datetime.datetime, datetime.date)):
            # PG version 12+ has better syntax for this statement
            if conn.server_version < 120000:
                values = [str(v) for v in values]
            partition_suffix = f"{partition_range[0].year}_{partition_range[0].month:02d}"
        else:
            partition_suffix = str(partition_range[0])

    sql = f"""
create table {target_schema}.{table_name}_{partition_suffix}
partition of {target_schema}.p_{table_name}
{range_clause};
"""
    LINFO(f"Creating table partition {target_schema}.{table_name}_{partition_suffix}...")
    execute(conn, f"drop table if exists {target_schema}.{table_name}_{partition_suffix};")
    execute(conn, sql, values)

    add_partition_track_record(
        conn,
        {
            "schema_name": target_schema,
            "table_name": f"{table_name}_{partition_suffix}",
            "partition_of_table_name": table_name,  # This is intentional!
            "partition_type": partition_type,
            "partition_col": partition_col,
            "partition_parameters": json_adapter(partition_parameters),
        },
    )


def drop_table(conn, schema_name, table_name):
    """
    Truncate, then drop a specified table
    Args:
        conn (Connection) : Database connection
        schema_name (str) : schema where the target table is located
        table_name (str) : name of the target table
    Returns:
        None
    """
    LINFO(f"Dropping table {schema_name}.{table_name}")
    execute(conn, f"truncate table {schema_name}.{table_name};")
    execute(conn, f"drop table {schema_name}.{table_name} cascade;")
    conn.commit()


def rename_source_sequences(conn, schema_name, table_name, sequence_info):
    """
    Rename source table sequences so that new sequences using the original names can be created.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Source table name
        sequence_info (list(NamedTuple)): Sequence information for the table as read from the database
    Returns:
        None
    """
    LINFO(f"Renaming sequences on source table {schema_name}.{table_name}")
    for s_spec in sequence_info:
        sql = f"""
alter sequence {s_spec.schemaname}.{s_spec.sequencename} rename to __{s_spec.sequencename} ;
"""
        execute(conn, sql)


def rename_source_views(conn, schema_name, table_name, view_info):
    """
    Rename views dependent on the source table so that new views using the original names can be created.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Source table name
        view_info (list(NamedTuple)): Sequence information for the table as read from the database
    Returns:
        None
    """
    LINFO(f"Renaming views for table {schema_name}.{table_name}")
    for v_spec in view_info:
        sql = f"""
alter {'materialized ' if v_spec.view_type == 'matview' else ''}view {v_spec.schemaname}.{v_spec.view_name}
rename to {'__' + v_spec.view_name} ;
"""
        execute(conn, sql)

        if v_spec.indexes:
            for ixname in v_spec.indexes.keys():
                sql = f"""
alter index {v_spec.schemaname}.{ixname} rename to {'__' + ixname}
"""
                execute(conn, sql)


def create_views(conn, schema_name, table_name, view_info):
    """
    Create views using the target partitioned table using the same name and definition as
    the original views on the source table.
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Source table name
        view_info (list(NamedTuple)): Sequence information for the table as read from the database
    Returns:
        None
    """
    LINFO(f"Creating views for table {schema_name}.{table_name}")
    for v_spec in view_info:
        sql = f"""
create {'materialized ' if v_spec.view_type == 'matview' else ''}view {v_spec.schemaname}.{v_spec.view_name} as
{v_spec.definition}
"""
        execute(conn, sql)

        if v_spec.indexes:
            for ixdef in v_spec.indexes.values():
                execute(conn, ixdef)

    conn.commit()


def refresh_materialized_views(conn, view_info):
    """
    Scans the read view information for materialized views and executes a refresh with data
    Args:
        conn (Connection): Database connection
        view_info (list(NamedTuple)): Sequence information for the table as read from the database
    Returns:
        None
    """
    for v_spec in view_info:
        if v_spec.view_type == "matview":
            sql = f"""
refresh materialized view {v_spec.schemaname}.{v_spec.view_name} with data;
"""
            execute(conn, sql)

    conn.commit()


def rename_constraints(conn, schema_name, table_name, constraints, src_op, src_val, dst_op, dst_val):
    """
    Rename table constraints
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Source table name
        constraints (list(NamedTuple)): Constraint information for the table as read from the database
        src_op (str): either "add" or "strip" -- applied to the source constraint name
        src_val (str): String to add or use to determine how much to strip from the beginning
                       of the source constraint name
        dst_op (str): either "add" or "strip" -- applied to the destination constraint name
        dst_val (str): String to add or use to determine how much to strip from the beginning
                       of the destination constraint name
    Returns:
        None
    """

    def p_add(label, prefix):
        return prefix + label

    def p_strip(label, prefix):
        if label.startsiwth(prefix):
            ix = len(prefix)
            return label[ix:]
        else:
            return label

    src_xform = locals()["p_" + src_op.lower()]
    dst_xform = locals()["p_" + dst_op.lower()]

    for c_spec in constraints:
        sql = f"""
alter table {schema_name}.{table_name}
rename constraint {src_xform(c_spec.constraint_name, src_val)}
to {dst_xform(c_spec.constraint_name, dst_val)} ;
"""
        execute(conn, sql)


def rename_indexes(conn, schema_name, table_name, indexes, src_op, src_val, dst_op, dst_val):
    """
    Rename table indexes
    Args:
        conn (Connection): Database connection
        schema_name (str): Schema name
        table_name (str): Source table name
        indexes (list(NamedTuple)): Index information for the table as read from the database
        src_op (str): either "add" or "strip" -- applied to the source index name
        src_val (str): String to add or use to determine how much to strip from the beginning
                       of the source index name
        dst_op (str): either "add" or "strip" -- applied to the destination index name
        dst_val (str): String to add or use to determine how much to strip from the beginning
                       of the destination index name
    Returns:
        None
    """

    def i_add(label, prefix):
        return prefix + label

    def i_strip(label, prefix):
        if label.startsiwth(prefix):
            ix = len(prefix)
            return label[ix:]
        else:
            return label

    src_xform = locals()["i_" + src_op.lower()]
    dst_xform = locals()["i_" + dst_op.lower()]

    for i_spec in indexes:
        index_parts = INDEX_PARSER.findall(i_spec.indexdef)
        if index_parts:
            index_name = index_parts[0][1]
            sql = f"""
alter index {schema_name}.{src_xform(index_name, src_val)}
rename to {dst_xform(index_name, dst_val)} ;
"""
            execute(conn, sql)


def rename_tables(conn, source_schema, source_table, target_schema, target_table, table_info):
    """
    Lock source table
    Rename the source table to __<source>
    Rename the partitioned table to the source table.
    This function WILL execute a commit
    Args:
        conn (Connection) : Database connection
        source_schema (str) : schema of source table
        source_table (str) : name of source table
        target_schema (str) : schema of target table
        target_table (str) : name of target table
    Returns:
        None
    """
    constraint_info = table_info["constraints"]
    index_info = table_info["indexes"]
    view_info = table_info["views"]

    LINFO(f"Acquiring table lock on {source_schema}.{source_table}")
    execute(conn, "BEGIN;")  # Done on purpose for script generation

    execute(conn, f"lock table {source_schema}.{source_table};")

    # Rename source table views
    LINFO(f"Rename {source_schema}.{source_table} views")
    rename_source_views(conn, source_schema, source_table, view_info)

    # Rename source table constraints from <cnst_name> to __<cnst_name>
    LINFO(f"Rename {source_schema}.{source_table} constraints")
    rename_constraints(conn, source_schema, source_table, constraint_info, "add", "", "add", "__")

    # Rename source table indexes from <idx_name> to __<idx_name>
    LINFO(f"Rename {source_schema}.{source_table} indexes")
    rename_indexes(conn, source_schema, source_table, index_info, "add", "", "add", "__")

    # Rename tables
    LINFO(f"Rename {source_schema}.{source_table} to {source_schema}.__{source_table}")
    execute(conn, f"alter table {source_schema}.{source_table} rename to __{source_table};")
    LINFO(f"Rename {target_schema}.{target_table} to {target_schema}.{source_table}")
    execute(conn, f"alter table {target_schema}.{target_table} rename to {source_table};")

    # Rename target table constraints from <cnst_name> to __<cnst_name>
    LINFO(f"Rename {target_schema}.{source_table} constraints")
    rename_constraints(conn, target_schema, source_table, constraint_info, "add", "p_", "add", "")

    # Rename target table indexes from <idx_name> to __<idx_name>
    LINFO(f"Rename {target_schema}.{source_table} indexes")
    rename_indexes(conn, target_schema, source_table, index_info, "add", "p_", "add", "")

    execute(conn, "COMMIT;")  # Done on purpose for script generation


def copy_data(conn, source_schema, source_table, target_schema, target_table, table_info):
    """
    Copy data from the source table and into the target table
    Args:
        conn (Connection) : Database connection
        source_schema (str) : schema of source table
        source_table (str) : name of source table
        target_schema (str) : schema of target table
        target_table (str) : name of target table
    Returns:
        None
    """
    LINFO(f"Copy data from {source_schema}.{source_table} to {target_schema}.{target_table}")
    column_map = table_info["partition_info"].get("copy_column_map")
    if column_map:
        insert_cols, select_cols = zip(*column_map.items())
        sql = f"""
insert into {target_schema}.{target_table} ( {', '.join(insert_cols)} )
select {', '.join(select_cols)} from {source_schema}.{source_table} ;
"""
    else:
        sql = f"insert into {target_schema}.{target_table} select * from {source_schema}.{source_table};"

    execute(conn, sql)


def create_stored_procedures(conn, schema, config):
    """
    Execute sql meant to define stored procedures against a schema
    Args:
        conn (Connection): Database connection
        schema (str): Schema name
        config (dict): Partition configuration settings
    Returns:
        None
    """
    sp_spec = config.get("stored_procedures", {})
    if sp_spec:
        schema_sp = sp_spec.get(schema, sp_spec.get("*", {}))
        if schema_sp:
            LINFO(f"Creating stored procedures for schema {schema}")
            if not schema_sp.get("processed", False):
                parent_schema = schema_sp.get("depends_on_schema")
                if parent_schema:
                    create_stored_procedures(conn, parent_schema, config)

                for sql in schema_sp["code"]:
                    execute(conn, sql.format(schema_name=schema))

                if schema not in sp_spec:
                    schema_sp = {"code": schema_sp["code"]}
                    sp_spec[schema] = schema_sp

                schema_sp["processed"] = True
            else:
                LINFO(f"Stored procedures for schema {schema} have already been processed")
        else:
            LINFO(f"No stored procedures for schema {schema}")


def process_database(db_url, config, sqlfilename=""):
    """
    Processes a database based on the partitioning configuration settings
    Args:
        db_url (str) : The connection string for the database in URL format
        config (dict) : Configuration for the partitioning. See comment at top of file
        sqlfilename (str) : name of a sql file to write commands instead of executing them
    Returns:
        None
    """
    global SQL_SCRIPT_FILE

    if not db_url:
        raise ValueError(f'Bad value for db_url: "{db_url}"')

    if not config:
        raise ValueError("Bad or empty config dict")

    if sqlfilename:
        SQL_SCRIPT_FILE = open(sqlfilename, "wt")
    try:
        with connect(db_url) as conn:
            for schema in db_schemas(conn):
                execute(conn, f"set search_path = {schema} ;")
                create_stored_procedures(conn, schema, config)
                if get_partition_targets(config, schema):
                    create_partition_table_tracker(conn, schema)
                    for table_info in partition_table_targets(conn, schema, config):
                        partition_table(conn, schema, table_info)
                else:
                    LINFO(f"No partitioning info for schema {schema}")
    finally:
        if SQL_SCRIPT_FILE:
            SQL_SCRIPT_FILE.flush()
            SQL_SCRIPT_FILE.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--database",
        dest="db_url",
        metavar="DB_URL",
        required=False,
        default="",
        help="Database connection string in URL form.",
    )
    parser.add_argument(
        "-c", "--config", dest="config", metavar="CONF", required=False, default="", help="Path to config file (YAML)"
    )
    parser.add_argument(
        "-g",
        "--gen-sample-config",
        action="store_true",
        dest="gen_config",
        required=False,
        default=False,
        help="Generate a sample configuration to stdout",
    )
    parser.add_argument(
        "-s",
        "--sql",
        dest="sqlfile",
        required=False,
        metavar="SQLFILE",
        default="",
        help="Generate a sql script instead of executing commands",
    )
    parser.add_argument(
        "--log",
        dest="loglevel",
        required=False,
        metavar="LOGLEVEL",
        choices=["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level. Default is INFO.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.loglevel, logging.INFO),
        style="{",
        format="{filename}:{asctime}:{levelname}:{message}",
    )

    LOG = logging.getLogger(os.path.basename(sys.argv[0]))
    LINFO = LOG.info
    LERROR = LOG.error
    LWARN = LOG.warning
    LDEBUG = LOG.debug

    if args.gen_config:
        generate_sample_config()
    else:
        if not args.config:
            raise ValueError("Empty config file name.")
        process_database(args.db_url, load_config(args.config), args.sqlfile)
