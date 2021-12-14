#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
import json
import logging
import os
import random
import re
import string
import time
import uuid

import ciso8601
from dateutil.relativedelta import relativedelta
from django.db import connection as conn
from django.db import transaction
from tenant_schemas.utils import schema_context

from koku.database import get_model


random.seed(time.time())
PartitionedTable = get_model("PartitionedTable")


# If this is detected, the code will try to resolve this to a name
# because, in some functionality, this needs to be a string vs the
# keyword.
CURRENT_SCHEMA = "current_schema"
BIGINT = "bigint"
INT = "int"

PARTITION_RANGE = "RANGE"
PARTITION_LIST = "LIST"

# This value from pg_class.relkind denotes a materialized view
VIEW_TYPE_MATERIALIZED = "MVIEW"

LOG = logging.getLogger(__name__)
# SQLFILE = open('/tmp/pg_partition.sql', 'wt')

_TEMPLATE_SCHEMA = os.environ.get("TEMPLATE_SCHEMA", "template0")


# Standardized SQL executor
def conn_execute(sql, params=None, _conn=conn):
    """
    Executes the given sql with any given parameters. This utilized the django.db.connection.
    Params
        sql (str) : SQL string
        params (list) : Parameters for SQL
    Returns:
        Cursor (if a SQL string was passed in)
        None   (if no SQL string was passed in or empty string)
    """
    if sql:
        cursor = _conn.cursor()
        LOG.debug(f"SQL: {cursor.mogrify(sql, params).decode('utf-8')}")
        # print(cursor.mogrify(sql, params).decode('utf-8') + '\n', file=SQLFILE, flush=True)
        cursor.execute(sql, params)
        return cursor
    else:
        return None


# Standardized fetch all routine that will return list(dict)
def fetchall(cursor):
    """
    Fetch all rows from the given cursor
    Params:
        cursor (Cursor) : Cursor of previously executed statement
    Returns:
        list(dict) : List of dict representing the records selected indexed by column name
    """
    if cursor:
        cursor_def = [d.name for d in cursor.description]
        return [dict(zip(cursor_def, r)) for r in cursor.fetchall()]
    else:
        return []


# Standardized fetch that will return dict
def fetchone(cursor):
    """
    Fetch one row from the given cursor
    Params:
        cursor (Cursor) : Cursor of previously executed statement
    Returns:
        dict : Dict representing the records selected indexed by column name
    """
    if cursor:
        return dict(zip((d.name for d in cursor.description), cursor.fetchone()))
    else:
        return {}


# Resolve "current_schema" to an actual schema name
def resolve_schema(schema):
    """
    Resolve CURRENT_SCHEMA to an actual schema name
    Params:
        schema (str) : schema name or CURRENT_SCHEMA
    Returns:
        str : Actual schema for CURRENT_SCHEMA or the input schema parameter
    """
    if schema == CURRENT_SCHEMA:
        cur = conn_execute('select current_schema as "current_schema";')
        schema = cur.fetchone()[0]

    LOG.info(f"Resolve schema is {schema}")
    return schema


# Wrapper for a default value for a column to be used in the column definition
class Default:
    """
    Interface to a default value to be used when a column definition needs a default value
    """

    def __init__(self, default_value):
        self.default_value = default_value

    def __str__(self):
        dval = None
        if self.default_value is None:
            dval = "null"
        elif hasattr(self.default_value, "default_constraint"):
            dval = self.default_value.default_constraint()
        else:
            dval = str(self.default_value)

        LOG.debug(f"""default value is: "{dval}" """)
        return dval

    def __repr__(self):
        return str(self)

    def __bool__(self):
        return True


# Possible future use
# class NoDefault:
#     def default_constraint(self):
#         return ""

#     def __str__(self):
#         return ""

#     def __repr__(self):
#         return ""


# Model a schema definition
class SequenceDefinition:
    """
    Model a schema definition. Includes some commans for create, alter owner/owned and setval.
    """

    NOMAXVALUE = "NO MAXVALUE"
    NOMINVALUE = "NO MINVALUE"
    CYCLE = "CYCLE"
    NO_CYCLE = "NO CYCLE"

    def __init__(
        self,
        target_schema,
        name,
        copy_sequence={},
        data_type=BIGINT,
        min_value=1,
        max_value=NOMAXVALUE,
        start_with=1,
        increment_by=1,
        cache=100,
        cycle=NO_CYCLE,
        current_value=1,
        owner=None,
    ):
        """
        Initialize a SchemaDefinition
        Params:
            target_schema (str) : schema name in which this new sequence will reside
            name (str) : name of sequence
            copy_sequence (dict) : Dict detailing a sequence to copy by specifying its owned-by column
                                   This dict should have the following keys:
                                       schema_name : Name of schema containing owner table
                                       table_name  : Name of owner table
                                       column_name : Name of owned-by column
            data_type (str) : data type of sequence (default is BIGINT)
            min_value (int/CONST) : minimum value (default is 1) NOMINVALUE const can be used
            max_value (int/CONST) : maximum value (default is NOMAXVALUE const)
            start_with (int) : Starting value (default is 1)
            increment_by (int) : Incerement-by value (default is 1)
            cache (int) : Number of values to cache (default is 100)
            cycle (CONST) : One of NO_CYCLE or CYCLE (defualt is NO_CYCLE)
            current_value (int) : Set the current value if this value is different from start_with
            owner (str) : name of the sequence owner
        """
        self.target_schema = resolve_schema(target_schema)
        self.name = name
        self.data_type = data_type
        self.min_value = min_value
        self.max_value = max_value
        self.start_with = start_with
        self.increment_by = increment_by
        self.cache = cache
        self.cycle = cycle
        self.owner = owner
        self.current_value = current_value

        if copy_sequence:
            self.copy_from(copy_sequence)

    def copy_from(self, source_sequence):
        """
        Reinitialize the SequenceDefinition from an existing sequence identified by
        its owned-by column reference <schema>.<table>.<column>
        Params:
            source_sequence (dict) : Dict detailing a sequence to copy by specifying its owned-by column
                                     This dict should have the following keys:
                                         schema_name : Name of schema containing owner table
                                         table_name  : Name of owner table
                                         column_name : Name of owned-by column
        Returns:
            None
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
 where ts.nspname = %s
   and t.relname = %s
   and a.attname = %s
   and d.classid = 'pg_class'::regclass;
"""
        LOG.info("Re-initialize sequence by copying specified existing sequence")
        cur = conn_execute(
            sql, [source_sequence["schema_name"], source_sequence["table_name"], source_sequence["column_name"]]
        )
        rec = fetchone(cur)
        self.data_type = rec["data_type"]
        self.min_value = rec["min_value"]
        self.max_value = rec["max_value"]
        self.start_with = rec["start_value"]
        self.increment_by = rec["increment_by"]
        self.cache = rec["cache_size"]
        self.cycle = self.CYCLE if rec["cycle"] else self.NO_CYCLE
        self.current_value = rec["last_value"] or 1
        self.owner = rec["sequenceowner"].strip('"')

    def default_constraint(self):
        return f"nextval('{self.target_schema}.{self.name}'::regclass)"

    def alter_owner(self):
        LOG.info("Running alter sequence owner")
        if self.owner:
            return f"""
ALTER SEQUENCE "{self.target_schema}"."{self.name}"
      OWNER TO "{self.owner}" ;
"""
        else:
            return ""

    def alter_owned_by(self, owner):
        LOG.info("Running alter sequence owned-by column")
        return f"""
ALTER SEQUENCE "{self.target_schema}"."{self.name}"
      OWNED BY "{owner["schema_name"]}"."{owner["table_name"]}"."{owner["column_name"]}" ;
"""

    def setval(self):
        if self.current_value and self.current_value > self.start_with:
            LOG.info("Running sequence setval")
            return (
                """
select setval(%s::regclass, %s);
""",
                (self.target_schema + "." + self.name, self.current_value),
            )
        else:
            return ("", None)

    def create(self):
        LOG.info("Running create sequence")
        return f"""
CREATE SEQUENCE "{self.target_schema}"."{self.name}"
       AS {self.data_type}
       INCREMENT BY {self.increment_by}
       MINVALUE {self.min_value}
       MAXVALUE {self.max_value}
       START WITH {self.start_with}
       CACHE {self.cache}
       {self.cycle} ;
"""


class ColumnDefinition:
    """
    Define changes to an existing table column that will be applied to the target partitioned table
    """

    def __init__(self, target_schema, target_table, column_name, data_type=None, using=None, null=None, default=None):
        """
        Initialize a column definition
        Params:
            target_schema (str) : schema containing the target table
            target_table (str) : name of target table
            column_name (str) : name of target column
            data_type (str) : database data type (default is None)
            using (str) : expression (if needed) to convert existing data to new data type
            null (bool) : True = remove not null constraint; false = apply not null; default is None
            default (Default) : The default value to apply. default is None
        """
        self.target_schema = target_schema
        self.target_table = target_table
        self.column_name = column_name
        self.data_type = data_type
        self.using = using
        self.null = null
        self.default = default

    def alter_column(self):
        LOG.info("Running alter column for column definiton")
        if not (bool(self.data_type) or bool(self.null) or bool(self.default)):
            return ""

        alters = []
        sql = f"""
ALTER TABLE "{self.target_schema}"."{self.target_table}"
"""
        # Possible future use
        #         if self.data_type:
        #             using = f"USING {self.using}" if self.using else ""
        #             alters.append(
        #                 f"""      ALTER COLUMN "{self.column_name}" SET DATA TYPE {self.data_type} {using}
        # """
        #             )
        #         if self.null is not None:
        #             alters.append(
        #                 f"""      ALTER COLUMN "{self.column_name}" SET {'NULL' if self.null else 'NOT NULL'}
        # """
        #             )
        if self.default:
            LOG.info("Setting default value")
            alters.append(
                f"""      ALTER COLUMN "{self.column_name}" SET DEFAULT {self.default}
"""
            )
        sql += ", ".join(alters) + ";"
        return sql


class ConstraintDefinition:
    """
    Define a constraint. This is used internally to copy contstraint information
    """

    def __init__(self, target_schema, target_table, constraintrec):
        self.target_schema = target_schema
        self.target_table = target_table
        self.constraint_type = constraintrec["constraint_type"]
        self.constraint_columns = constraintrec["constraint_columns"]
        self.constraint_name = constraintrec["constraint_name"]
        self.definition = constraintrec["definition"]

    def alter_add_constraint(self):
        LOG.info(f"Runing ALTER TABLE ADD CONSTRAINT p_{self.constraint_name}")
        sql = f"""
ALTER TABLE "{self.target_schema}"."{self.target_table}"
      ADD CONSTRAINT "p_{self.constraint_name}" {self.definition} ;
"""
        return sql


class PKDefinition:
    """
    Define a primary key for the partitioned table. This is intended to facilitate a composite key
    """

    def __init__(self, name, column_names):
        """
        Initialize a PKDefinition
        Params:
            name (str) : Name of the primary key constraint
            column_names (list(str)) : list of primary key columns that will be created in list order
        """
        self.column_names = column_names
        self.name = name

    def alter_table(self, schema_name, table_name):
        LOG.info("Adding PRIMARY KEY constraint")
        column_names = ",".join(self.column_names)
        return f"""
ALTER TABLE "{schema_name}"."{table_name}"
      ADD CONSTRAINT "{self.name}"
      PRIMARY KEY ({column_names}) ;
"""


class IndexDefinition:
    """
    Index definition from the source table that will be reapplied to the target table
    This is used internally during the conversion process
    """

    INDEX_PARSER = re.compile("(^.+INDEX )(.+)( ON )(.+)( USING.+$)", flags=re.IGNORECASE)
    INDEX_NAME_IX = 1
    INDEX_TABLE_IX = -2

    def __init__(self, target_schema, target_table, indexrec):
        self.target_schema = target_schema
        self.target_table = target_table
        self.schema_name = indexrec["schemaname"]
        self.table_name = indexrec["tablename"]
        self.index_name = indexrec["indexname"]
        self.index_columns = indexrec["indexcols"]
        self.is_unique = indexrec["indisunique"]
        self.definition = indexrec["indexdef"]

        if ";" not in self.definition[:-10]:
            self.definition += " ;"

    def create(self):
        index_parts = self.INDEX_PARSER.findall(self.definition)
        if index_parts:
            LOG.info(f'Creating index "p_{self.index_name}"')
            index_parts = list(index_parts[0])
            index_parts[0] += "IF NOT EXISTS "
            index_parts[self.INDEX_NAME_IX] = f"p_{self.index_name}"
            index_parts[self.INDEX_TABLE_IX] = f"{self.target_schema}.{self.target_table}"
            return " ".join(index_parts)
        else:
            LOG.error(f"ERROR parsing index definition for {self.index_name} [[ {self.definition} ]]")

        return ""


class ViewDefinition:
    """
    Definition of a dependent view of the source table that will be reapplied to the target table
    This does handle single-level dependencies, but has not been tested fully on nested views.
    This is used internally during the conversion process to reapply views to the partitioned table.
    This handles "normal" views as well as materialized views.
    """

    def __init__(self, target_schema, viewrec):
        self.target_schema = target_schema
        self.level = viewrec["level"]
        self.schema_name = viewrec["source_schema"]
        self.table_name = viewrec["source_table"]
        self.view_schema = viewrec["dependent_schema"]
        self.view_schema_oid = viewrec["dependent_schema_oid"]
        self.view_name = viewrec["dependent_view"]
        self.view_oid = viewrec["dependent_view_oid"]
        self.view_type = viewrec["dependent_view_type"]
        self.definition = viewrec["definition"]
        self.view_owner = viewrec["dependent_view_owner"].strip('"')
        self.indexes = []
        for ixrec in viewrec["indexes"] or []:
            self.indexes.append(IndexDefinition(self.target_schema, self.view_name, ixrec))

        if ";" not in self.definition[:-10]:
            self.definition += " ;"

    def rename_original_view_indexes(self):
        return [
            f"""
ALTER INDEX "{vix.schema_name}"."{vix.index_name}"
RENAME TO "__{vix.index_name}" ;
"""
            for vix in self.indexes
        ]

    def rename_original_view(self):
        view_type = "MATERIALIZED" if self.view_type == VIEW_TYPE_MATERIALIZED else ""
        return f"""
ALTER {view_type} VIEW "{self.view_schema}"."{self.view_name}"
RENAME TO "__{self.view_name}" ;
"""

    def alter_owner(self):
        LOG.info("Alter view owner")
        view_type = "MATERIALIZED" if self.view_type == VIEW_TYPE_MATERIALIZED else ""
        sql = f"""
ALTER {view_type} VIEW "{self.target_schema}"."{self.view_name}"
      OWNER TO "{self.view_owner}" ;
"""
        return sql

    # Poosible future use
    #     def drop_target(self):
    #         LOG.info("Dropping target view")
    #         view_type = 'MATERIALIZED' if self.view_type == VIEW_TYPE_MATERIALIZED else ''
    #         sql = f"""
    # DROP {view_type} VIEW IF EXISTS "{self.target_schema}"."{self.view_name}" ;
    # """
    #         return sql

    #     def drop(self):
    #         view_type = 'MATERIALIZED' if self.view_type == VIEW_TYPE_MATERIALIZED else ''
    #         sql = f"""
    # DROP {view_type} VIEW IF EXISTS "{self.schema_name}"."{self.view_name}" ;
    # """
    #         return sql

    def create(self):
        view_type = "MATERIALIZED " if self.view_type == VIEW_TYPE_MATERIALIZED else ""
        LOG.info(f'Creating {view_type}VIEW "{self.view_name}')
        sql = f"""
CREATE {view_type} VIEW "{self.target_schema}"."{self.view_name}" AS
{self.definition}
"""
        return sql

    def refresh(self):
        LOG.info(f'Refresh materialized view "{self.view_name}"')
        sql = f"""
REFRESH MATERIALIZED VIEW "{self.target_schema}"."{self.view_name}" ;
"""
        return sql


class ConvertToPartition:
    """
    Driver class to facilitate the conversion of an existing table to a partitioned table
    with the same table definition, as well as duplicated constraint, sequence, index, and view definitions.
    """

    VIEW_DESTROY_ORDER = 0
    VIEW_CREATE_ORDER = 1

    def __init__(
        self,
        source_table_name,
        partition_key,
        partition_type=PARTITION_RANGE,
        target_table_name=None,
        pk_def=None,
        col_def=[],
        target_schema=CURRENT_SCHEMA,
        source_schema=CURRENT_SCHEMA,
    ):
        """
        Initialize the converter.
        Params:
            source_table_name (str) : name of source table
            partition_key (str) : column in source table to partiton on
            partition_type (CONST) : Use PARTITION_RANGE or PARTITON_LIST (default is PARTITION_RANGE)
            target_table_name (str) : name of target table (defualt is 'p_' + source_table_name)
            pk_def (PKDefinition) : Redefine primary key (default is None)
            col_def (list(ColumnDefinition)) : Redefine any column(s) (default is [])
            target_schema (str/CONST) : Schema to contain the partitioned table (default is CURRENT_SCHEMA)
            source_schema (str/CONST) : Schema containing the source table (default is CURRENT_SCHEMA)
        """
        self.conn = conn
        self.target_schema = resolve_schema(target_schema)
        self.partitioned_table_name = target_table_name or ("p_" + source_table_name)
        self.partition_key = partition_key
        self.partition_type = partition_type
        self.source_schema = resolve_schema(source_schema)
        self.source_table_name = source_table_name
        self.pk_def = pk_def
        self.col_def = col_def
        self.indexes = self.__get_indexes()
        self.constraints = self.__get_constraints()
        self.views = self.__get_views()
        self.__new_trigger = self.detect_new_manager_trigger()

    def __repr__(self):
        return f"""Convert "{self.source_schema}"."{self.source_table_name}" to a partitioned table"""

    def view_iter(self, order):
        if order == self.VIEW_DESTROY_ORDER:
            return iter(self.views)
        else:
            return reversed(self.views)

    def detect_new_manager_trigger(self):
        func_sql = """
select oid
  from pg_proc
 where pronamespace = 'public'::regnamespace
   and proname = 'trfn_partition_manager';
"""
        trgr_sql = f"""
select oid
  from pg_trigger
 where tgrelid = '"{self.target_schema}"."partitioned_tables"'::regclass
   and tgfoid = %s
   and tgname = 'tr_partition_manager' ;
"""
        func_oid = (conn_execute(func_sql).fetchone() or [None])[0]
        if func_oid:
            trgr_oid = (conn_execute(trgr_sql, (func_oid,)).fetchone() or [None])[0]
            res = bool(trgr_oid)
        else:
            res = False

        if res:
            LOG.info(f"{self.__class__.__name__}: Using trfn_partition_manager function")
        else:
            LOG.info(f"{self.__class__.__name__}: Using trfn_manage_date_range_partition function")

        return res

    def __get_constraints(self):
        LOG.info(f"Getting constraints for table {self.source_schema}.{self.source_table_name}")
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
   and n.nspname = %s
   and t.relname = %s
 order
    by t.relname,
       case when c.contype = 'p'
                 then 0
            else 1
       end::int
"""
        cur = conn_execute(sql, [self.source_schema, self.source_table_name])
        return [
            ConstraintDefinition(self.target_schema, self.partitioned_table_name, rec)
            for rec in fetchall(cur)
            if rec["constraint_type"] != "p"
        ]

    def __get_indexes(self):
        LOG.info(f"Getting indexes for table {self.source_schema}.{self.source_table_name}")
        sql = """
select n.nspname::text as "schemaname",
       t.relname::text as "tablename",
       ix.relname::text as "indexname",
       i.indisunique,
       i.indisprimary,
       (
           select array_agg(_a.attname)
             from pg_attribute _a
            where _a.attrelid = t.oid
              and _a.attnum = any(i.indkey)
       )::text[] as "indexcols",
       pg_get_indexdef(i.indexrelid) as "indexdef"
  from pg_class t
  join pg_namespace n
    on n.oid = t.relnamespace
  join pg_index i
    on i.indrelid = t.oid
  join pg_class ix
    on ix.oid = i.indexrelid
 where n.nspname = %s
   and t.relname = %s
   and not i.indisprimary
 order
    by t.relname;
"""
        params = [self.source_schema, self.source_table_name]
        cur = conn_execute(sql, params)
        return [IndexDefinition(self.target_schema, self.partitioned_table_name, rec) for rec in fetchall(cur)]

    def __get_views(self):
        LOG.info(f"Getting views referencing table {self.source_schema}.{self.source_table_name}")
        hierarchy_sql = """
WITH RECURSIVE preference AS (
  SELECT 10 AS max_depth  -- The deeper the recursion goes, the slower it performs.
    , 16384 AS min_oid -- user objects only
    , '^(londiste|pgq|pg_toast)'::text AS schema_exclusion
    , '^pg_(conversion|language|ts_(dict|template))'::text AS class_exclusion
    , '{"SCHEMA":"00", "TABLE":"01", "CONSTRAINT":"02", "DEFAULT":"03",
        "INDEX":"05", "SEQUENCE":"06", "TRIGGER":"07", "FUNCTION":"08",
        "VIEW":"10", "MVIEW":"11", "FOREIGN":"12"}'::json AS type_ranks
)
, dependency_pair AS (
    WITH relation_object AS (
        SELECT oid
        , oid::regclass::text AS object_name
        , CASE relkind
              WHEN 'r' THEN 'TABLE'::text
              WHEN 'i' THEN 'INDEX'::text
              WHEN 'S' THEN 'SEQUENCE'::text
              WHEN 'v' THEN 'VIEW'::text
              WHEN 'm' THEN 'MVIEW'::text
              WHEN 'c' THEN 'TYPE'::text      -- COMPOSITE type
              WHEN 't' THEN 'TOAST'::text
              WHEN 'f' THEN 'FOREIGN'::text
          END AS object_type
        FROM pg_class
    )
    select
        case when classid = 'pg_rewrite'::regclass
             THEN (SELECT e.ev_class FROM pg_rewrite e WHERE e.oid = objid)
             else objid
        end::oid objid,
        CASE classid
            WHEN 'pg_amop'::regclass THEN 'ACCESS METHOD OPERATOR'
            WHEN 'pg_amproc'::regclass THEN 'ACCESS METHOD PROCEDURE'
            WHEN 'pg_attrdef'::regclass THEN 'DEFAULT'
            WHEN 'pg_cast'::regclass THEN 'CAST'
            WHEN 'pg_class'::regclass THEN rel.object_type
            WHEN 'pg_constraint'::regclass THEN 'CONSTRAINT'
            WHEN 'pg_extension'::regclass THEN 'EXTENSION'
            WHEN 'pg_namespace'::regclass THEN 'SCHEMA'
            WHEN 'pg_opclass'::regclass THEN 'OPERATOR CLASS'
            WHEN 'pg_operator'::regclass THEN 'OPERATOR'
            WHEN 'pg_opfamily'::regclass THEN 'OPERATOR FAMILY'
            WHEN 'pg_proc'::regclass THEN 'FUNCTION'
            WHEN 'pg_rewrite'::regclass THEN (SELECT concat(object_type,' RULE(' || objid::text || ')') FROM pg_rewrite e JOIN relation_object r ON r.oid = ev_class WHERE e.oid = objid)
            WHEN 'pg_trigger'::regclass THEN 'TRIGGER'
            WHEN 'pg_type'::regclass THEN 'TYPE'
            ELSE classid::regclass::text
        END AS object_type,
        CASE classid
            WHEN 'pg_attrdef'::regclass THEN (SELECT attname FROM pg_attrdef d JOIN pg_attribute c ON (c.attrelid,c.attnum)=(d.adrelid,d.adnum) WHERE d.oid = objid)
            WHEN 'pg_cast'::regclass THEN (SELECT concat(castsource::regtype::text, ' AS ', casttarget::regtype::text,' WITH ', castfunc::regprocedure::text) FROM pg_cast WHERE oid = objid)
            WHEN 'pg_class'::regclass THEN rel.object_name
            WHEN 'pg_constraint'::regclass THEN (SELECT conname FROM pg_constraint WHERE oid = objid)
            WHEN 'pg_extension'::regclass THEN (SELECT extname FROM pg_extension WHERE oid = objid)
            WHEN 'pg_namespace'::regclass THEN (SELECT nspname FROM pg_namespace WHERE oid = objid)
            WHEN 'pg_opclass'::regclass THEN (SELECT opcname FROM pg_opclass WHERE oid = objid)
            WHEN 'pg_operator'::regclass THEN (SELECT oprname FROM pg_operator WHERE oid = objid)
            WHEN 'pg_opfamily'::regclass THEN (SELECT opfname FROM pg_opfamily WHERE oid = objid)
            WHEN 'pg_proc'::regclass THEN objid::regprocedure::text
            WHEN 'pg_rewrite'::regclass THEN (SELECT ev_class::regclass::text FROM pg_rewrite WHERE oid = objid)
            WHEN 'pg_trigger'::regclass THEN (SELECT tgname FROM pg_trigger WHERE oid = objid)
            WHEN 'pg_type'::regclass THEN objid::regtype::text
            ELSE objid::text
        END AS object_name,
        array_agg(objsubid ORDER BY objsubid) AS objsubids,
        refobjid,
        CASE refclassid
            WHEN 'pg_namespace'::regclass THEN 'SCHEMA'
            WHEN 'pg_class'::regclass THEN rrel.object_type
            WHEN 'pg_opfamily'::regclass THEN 'OPERATOR FAMILY'
            WHEN 'pg_proc'::regclass THEN 'FUNCTION'
            WHEN 'pg_type'::regclass THEN 'TYPE'
            ELSE refclassid::text
        END AS refobj_type,
        CASE refclassid
            WHEN 'pg_namespace'::regclass THEN (SELECT nspname FROM pg_namespace WHERE oid = refobjid)
            WHEN 'pg_class'::regclass THEN rrel.object_name
            WHEN 'pg_opfamily'::regclass THEN (SELECT opfname FROM pg_opfamily WHERE oid = refobjid)
            WHEN 'pg_proc'::regclass THEN refobjid::regprocedure::text
            WHEN 'pg_type'::regclass THEN refobjid::regtype::text
            ELSE refobjid::text
        END AS refobj_name,
        array_agg(refobjsubid ORDER BY refobjsubid) AS refobjsubids,
        CASE deptype
            WHEN 'n' THEN 'normal'
            WHEN 'a' THEN 'automatic'
            WHEN 'i' THEN 'internal'
            WHEN 'e' THEN 'extension'
            WHEN 'p' THEN 'pinned'
        END AS dependency_type
    FROM pg_depend dep
    LEFT JOIN relation_object rel ON rel.oid = dep.objid
    LEFT JOIN relation_object rrel ON rrel.oid = dep.refobjid
    left join pg_class cls on dep.objid = cls.oid
    , preference
    WHERE deptype = ANY('{n,a}')
    AND objid >= preference.min_oid
    AND (refobjid >= preference.min_oid OR refobjid = 2200) -- need public schema as root node
    AND classid::regclass::text !~ preference.class_exclusion
    AND refclassid::regclass::text !~ preference.class_exclusion
    AND coalesce(substring(objid::regclass::text, E'^(\\w+)\\.'),'') !~ preference.schema_exclusion
    AND coalesce(substring(refobjid::regclass::text, E'^(\\w+)\\.'),'') !~ preference.schema_exclusion
    GROUP BY classid, objid, refclassid, refobjid, deptype, rel.object_name, rel.object_type, rrel.object_name, rrel.object_type
)
, dependency_hierarchy AS (
    SELECT DISTINCT
        0 AS level,
        refobjid AS objid,
        refobj_type AS object_type,
        refobj_name AS object_name,
        NULL::text AS dependency_type,
        ARRAY[refobjid] AS dependency_chain,
        ARRAY[concat(preference.type_ranks->>refobj_type,refobj_type,' ',refobj_name)] AS dependency_name_chain
    FROM dependency_pair root
    , preference
    WHERE NOT EXISTS
       (SELECT 'x' FROM dependency_pair branch WHERE branch.objid = root.refobjid)
    AND refobj_name !~ preference.schema_exclusion
    UNION ALL
    SELECT
        level + 1 AS level,
        child.objid,
        child.object_type,
        child.object_name,
        child.dependency_type,
        parent.dependency_chain || child.objid,
        parent.dependency_name_chain || concat(preference.type_ranks->>child.object_type,child.object_type,' ',child.object_name)
    FROM dependency_pair child
    JOIN dependency_hierarchy parent ON (parent.objid = child.refobjid)
    , preference
    WHERE level < preference.max_depth
    AND child.object_name !~ preference.schema_exclusion
    AND child.refobj_name !~ preference.schema_exclusion
    AND NOT (child.objid = ANY(parent.dependency_chain)) -- prevent circular referencing
)
SELECT level,
       case when object_type = 'SCHEMA'
            then objid
            else cls.relnamespace
       end::oid nspid,
       case when object_type = 'SCHEMA'
            then object_name
            else cls.relnamespace::regnamespace::text
       end::text namespace_name,
       objid,
       object_type,
       object_name,
       cls.relowner::regrole::text object_owner,
       dependency_chain,
       dependency_name_chain,
       case when object_type ~ '^M*VIEW'
            then (
                     select array_agg(row_to_json(vi))
                       from (
                                select _t.relnamespace::regnamespace::text as "schemaname",
                                       _t.relname::text as "tablename",
                                       _ix.relname::text as "indexname",
                                       _i.indisunique,
                                       _i.indisprimary,
                                       (
                                            select array_agg(_a.attname)
                                              from pg_attribute _a
                                             where _a.attrelid = _t.oid
                                               and _a.attnum = any(_i.indkey)
                                       )::text[] as "indexcols",
                                       pg_get_indexdef(_i.indexrelid) as "indexdef"
                                  from pg_class _t
                                  join pg_index _i
                                    on _i.indrelid = _t.oid
                                  join pg_class _ix
                                    on _ix.oid = _i.indexrelid
                                 where _t.oid = dependency_hierarchy.objid
                            ) vi
            )
            else null
       end::json[] as view_indexes,
       case when object_type ~ '^M*VIEW'
            then pg_get_viewdef(dependency_hierarchy.objid)
            else null
       end::text as view_definition
  FROM dependency_hierarchy
  left
  join pg_class cls
    on cls.oid = objid
 WHERE array_position(dependency_chain, %s::regclass::oid) is not null
   AND (object_type = ANY('{SCHEMA,TABLE}'::text[]) or
        object_type ~ '^M*VIEW RULE')
 ORDER BY level desc, dependency_chain ;
"""  # noqa:E501
        hierarchy = fetchall(conn_execute(hierarchy_sql, [f'"{self.source_schema}"."{self.source_table_name}"']))
        # The hierarchy will be stored with the lowest level first or in destroy-order
        res = []
        for entry in hierarchy:
            if entry["object_type"] == "TABLE":
                break
            if "." in entry["object_name"]:
                _, entry["object_name"] = entry["object_name"].split(".", 1)
            rec = {
                "level": entry["level"],
                "source_schema": self.source_schema,
                "source_table": self.source_table_name,
                "dependent_schema_oid": entry["nspid"],
                "dependent_schema": entry["namespace_name"],
                "dependent_view_oid": entry["objid"],
                "dependent_view_type": entry["object_type"].split()[0],
                "dependent_view": entry["object_name"],
                "definition": entry["view_definition"],
                "dependent_view_owner": entry["object_owner"],
                "indexes": entry["view_indexes"],
            }
            res.append(ViewDefinition(self.target_schema, rec))

        return res

    def __create_table_like_source(self):
        msg = f'Creating base table structure for "{self.target_schema}"."{self.partitioned_table_name}" from '
        msg += f'"{self.source_schema}"."{self.source_table_name}"'
        LOG.info(msg)
        LOG.info(f'Partitioning by {self.partition_type} ( "{self.partition_key}" )')
        sql = f"""
CREATE TABLE IF NOT EXISTS "{self.target_schema}"."{self.partitioned_table_name}" (
    LIKE "{self.source_schema}"."{self.source_table_name}"
    INCLUDING DEFAULTS
    INCLUDING GENERATED
    INCLUDING IDENTITY
    INCLUDING STATISTICS
)
PARTITION BY {self.partition_type} ( "{self.partition_key}" ) ;
"""
        conn_execute(sql)

    def __create_default_partition_new(self):
        sql = f"""
INSERT INTO "{self.target_schema}"."partitioned_tables" (
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters
)
VALUES (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb
);
"""
        params = (
            self.target_schema,
            f"{self.source_table_name}_default",
            self.partitioned_table_name,
            self.partition_type.lower(),
            self.partition_key,
            '{"default": true}',
        )
        LOG.info(f'Creating and recording default partition "{self.target_schema}"."{self.source_table_name}_default"')
        conn_execute(sql, params)

    def __create_default_partition(self):
        LOG.info(f'Creating default partition "{self.target_schema}"."{self.source_table_name}_default"')
        sql = f"""
CREATE TABLE IF NOT EXISTS "{self.target_schema}"."{self.source_table_name}_default"
PARTITION OF "{self.target_schema}"."{self.partitioned_table_name}" DEFAULT ;
"""
        conn_execute(sql)

        LOG.debug("Recording default partition")
        sql = f"""
INSERT INTO "{self.target_schema}"."partitioned_tables" (
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters
)
VALUES (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb
);
"""
        params = (
            self.target_schema,
            f"{self.source_table_name}_default",
            self.partitioned_table_name,
            self.partition_type.lower(),
            self.partition_key,
            '{"default": true}',
        )
        conn_execute(sql, params)

    def __set_primary_key(self):
        LOG.info("Setting any primary key definition")
        if self.pk_def:
            conn_execute(self.pk_def.alter_table(self.target_schema, self.partitioned_table_name))

    def __set_column_definitions(self):
        LOG.info("Applying any column alterations")
        for cdef in self.col_def:
            default_is_sequence = hasattr(cdef, "default") and isinstance(
                cdef.default.default_value, SequenceDefinition
            )
            if default_is_sequence:
                conn_execute(cdef.default.default_value.create())
                conn_execute(*cdef.default.default_value.setval())

            conn_execute(cdef.alter_column())

            if default_is_sequence:
                conn_execute(cdef.default.default_value.alter_owner())
                owner = {
                    "schema_name": self.target_schema,
                    "table_name": self.partitioned_table_name,
                    "column_name": cdef.column_name,
                }
                conn_execute(cdef.default.default_value.alter_owned_by(owner))

    def __set_constraints(self):
        LOG.info("Applying any table constratins")
        for cdef in self.constraints:
            if cdef.constraint_type.lower() == "u" and not set(cdef.constraint_columns).isdisjoint(
                set(self.pk_def.column_names)
            ):
                LOG.warning(f"Unique constraint {cdef.constraint_name} overlaps with primary key and will be omitted.")
                continue
            else:
                LOG.info(f"Applying constraint {cdef.constraint_name}")
                conn_execute(cdef.alter_add_constraint())

    def __create_indexes(self):
        for idef in self.indexes:
            if idef.is_unique and not set(idef.index_columns).isdisjoint(set(self.pk_def.column_names)):
                LOG.warning(f"Unique index {idef.index_name} overlaps with primary key and will be omitted.")
                continue
            else:
                LOG.info(f"Applying index definition for {idef.index_name}")
                conn_execute(idef.create())

    def __get_partition_start_values(self, params):
        sql = """
select partition_start from scan_for_date_partitions(%s::text, %s::text, %s::text, %s::text);
"""
        cur = conn_execute(sql, params)
        requested_partitions = fetchall(cur)
        return requested_partitions

    def __get_partition_parameters_start_values(self, params):
        sql = f"""
select (partition_parameters->>'from')::date as existing_partition
  from "{self.target_schema}"."partitioned_tables"
 where schema_name = %s
   and partition_of_table_name = %s
   and table_name ~ %s
   and partition_parameters->>'default' = 'false';
"""
        cur = conn_execute(sql, params)
        existing_partitions = fetchall(cur)
        return existing_partitions

    def __get_needed_partitions(self, requested_partitions, existing_partitions):
        needed_partitions = {p["partition_start"] for p in requested_partitions} - {
            ciso8601.parse_datetime(p["partition_parameters"]["from"]).date() for p in existing_partitions
        }
        return needed_partitions

    def __create_partitions_new(self):
        created_partitions = []
        params = [
            f"{self.source_schema}.{self.source_table_name}",  # This will be quoted properly in the proc
            self.partition_key,
            self.target_schema,
            self.partitioned_table_name,
        ]
        requested_partitions = self.__get_partition_start_values(params)

        # Get existing partitions except the default partition
        params = [self.target_schema, self.partitioned_table_name, f"^{self.partitioned_table_name}"]
        existing_partitions = self.__get_partition_parameters_start_values(params)

        needed_partitions = self.__get_needed_partitions(requested_partitions, existing_partitions)

        part_rec_sql = f"""
INSERT INTO "{self.target_schema}"."partitioned_tables" (
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters
)
VALUES (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb
);
"""
        params = [
            self.target_schema,
            None,
            self.partitioned_table_name,
            self.partition_type.lower(),
            self.partition_key,
            None,
        ]
        part_params = {"default": False, "from": None, "to": None}
        for newpart in needed_partitions:
            part_params["from"] = str(newpart)
            part_params["to"] = str(newpart + relativedelta(months=1))
            suffix = newpart.strftime("%Y_%m")
            partition_name = f"{self.partitioned_table_name}_{suffix}"
            params[1] = partition_name
            params[-1] = json.dumps(part_params)
            LOG.info(f'Creating and recording partition "{self.target_schema}"."{partition_name}"')
            conn_execute(part_rec_sql, params)
            created_partitions.append({"table_name": partition_name, "suffix": suffix})

        self.created_partitions = created_partitions

    def __create_partitions(self):
        # Get "requested" partitions
        params = [
            f"{self.source_schema}.{self.source_table_name}",  # This will be quoted properly in the proc
            self.partition_key,
            self.target_schema,
            self.partitioned_table_name,
        ]
        requested_partitions = self.__get_partition_start_values(params)

        # Get existing partitions except the default partition
        params = [self.target_schema, self.partitioned_table_name, f"^{self.partitioned_table_name}"]
        existing_partitions = self.__get_partition_parameters_start_values(params)

        needed_partitions = self.__get_needed_partitions(requested_partitions, existing_partitions)

        sqltmpl = f"""
CREATE TABLE IF NOT EXISTS "{self.target_schema}"."{{table_partition}}"
PARTITION OF "{self.target_schema}"."{self.partitioned_table_name}"
FOR VALUES FROM (%s::date) TO (%s::date) ;
"""
        part_rec_sql = f"""
INSERT INTO "{self.target_schema}"."partitioned_tables" (
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters
)
VALUES (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb
);
"""
        for newpart in needed_partitions:
            params = (newpart, newpart + relativedelta(months=1))
            partition_name = f"{self.partitioned_table_name}_{newpart.strftime('%Y_%m')}"
            LOG.info(f"Creating partition {self.target_schema}.{partition_name}")
            conn_execute(sqltmpl.format(table_partition=partition_name), params)

            params = (
                self.target_schema,
                partition_name,
                self.partitioned_table_name,
                self.partition_type.lower(),
                self.partition_key,
                '{{"default": false, "from": "{0}", "to": "{1}"}}'.format(*params),
            )
            LOG.info(f"Recording partition {self.target_schema}.{partition_name}")
            conn_execute(part_rec_sql, params)

        # Get created partitions
        sql = f"""
select table_name,
       to_char(date(partition_parameters->>'from'), 'YYYY_MM') as suffix
  from "{self.target_schema}"."partitioned_tables"
 where schema_name = %s
   and partition_of_table_name = %s
   and table_name ~ %s ;
"""
        params = [self.target_schema, self.partitioned_table_name, f"^{self.partitioned_table_name}"]
        cur = conn_execute(sql, params)
        self.created_partitions = fetchall(cur)

    def __copy_data(self):
        c_from = f'"{self.target_schema}"."{self.partitioned_table_name}"'
        c_to = f'"{self.source_schema}"."{self.source_table_name}"'
        LOG.info(f"Copying data from {c_from} to {c_to}")
        sql = f"""
INSERT INTO "{self.target_schema}"."{self.partitioned_table_name}"
SELECT * FROM "{self.source_schema}"."{self.source_table_name}" ;
"""
        with transaction.atomic():
            conn_execute(sql)

    def __rename_objects_new(self):
        messages = [f'Locking source table "{self.source_schema}"."{self.source_table_name}"']
        sql_actions = [
            f"""
LOCK TABLE "{self.source_schema}"."{self.source_table_name}" ;
"""
        ]
        for vdef in self.views:
            actions = vdef.rename_original_view_indexes()
            messages.append(f'Renaming view indexes for "{vdef.view_schema}"."{vdef.view_name}"')
            messages.extend([None] * (len(actions) - 1))
            sql_actions.extend(actions)
            messages.append(f'Renaming view "{vdef.view_schema}"."{vdef.view_name}" to "__{vdef.view_name}"')
            sql_actions.append(vdef.rename_original_view())

        messages.append(
            f'Renaming source table "{self.source_schema}"."{self.source_table_name}"'
            f' to "__{self.source_table_name}"'
        )
        sql_actions.append(
            f"""
ALTER TABLE "{self.source_schema}"."{self.source_table_name}"
RENAME TO "__{self.source_table_name}" ;
"""
        )
        messages.append(
            f'Renaming partitioned table "{self.target_schema}"."{self.partitioned_table_name}"'
            f' to "{self.source_table_name}"'
        )
        sql_actions.append(
            (
                f"""
UPDATE "{self.target_schema}".partitioned_tables
   SET partition_of_table_name = %s
 WHERE schema_name = %s
   AND partition_of_table_name = %s;
""",
                (self.source_table_name, self.target_schema, self.partitioned_table_name),
            )
        )
        for partition in self.created_partitions:
            r_partition_name = f'{self.source_table_name}_{partition["suffix"]}'
            messages.append(
                f'''Renaming table partition "{self.target_schema}"."{partition['table_name']}"'''
                f' to "{r_partition_name}"'
            )
            sql_actions.append(
                (
                    f"""
UPDATE "{self.target_schema}".partitioned_tables
   SET table_name = %s
 WHERE schema_name = %s
   AND partition_of_table_name = %s
   AND table_name = %s;
""",
                    (r_partition_name, self.target_schema, self.source_table_name, partition["table_name"]),
                )
            )

        for ix in range(len(sql_actions)):
            msg = messages[ix]
            if msg:
                LOG.info(msg)

            sql = sql_actions[ix]
            if isinstance(sql, tuple):
                sql, params = sql
            else:
                params = None

            LOG.debug(f"SQL = {sql}  PARAMS = {params}")
            conn_execute(sql, params)

        self.partitioned_table_name = self.source_table_name
        self.source_table_name = f"__{self.source_table_name}"

    def __rename_objects(self):
        LOG.info(f'Locking source table "{self.source_schema}"."{self.source_table_name}"')
        sql_actions = [
            f"""
LOCK TABLE "{self.source_schema}"."{self.source_table_name}" ;
"""
        ]
        for vdef in self.views:
            LOG.info(f'Renaming view indexes for "{vdef.view_schema}"."{vdef.view_name}"')
            sql_actions.extend(vdef.rename_original_view_indexes())
            LOG.info(f'Renaming view "{vdef.view_schema}"."{vdef.view_name}" to "__{vdef.view_name}"')
            sql_actions.append(vdef.rename_original_view())

        msg = (
            f'Renaming source table "{self.source_schema}"."{self.source_table_name}"'
            f' to "__{self.source_table_name}"'
        )
        LOG.info(msg)
        sql_actions.append(
            f"""
ALTER TABLE "{self.source_schema}"."{self.source_table_name}"
RENAME TO "__{self.source_table_name}" ;
"""
        )
        msg = (
            f'Renaming partitioned table "{self.target_schema}"."{self.partitioned_table_name}"'
            f' to "{self.source_table_name}"'
        )
        LOG.info(msg)
        sql_actions.append(
            f"""
ALTER TABLE "{self.target_schema}"."{self.partitioned_table_name}"
RENAME TO "{self.source_table_name}" ;
"""
        )
        for partition in self.created_partitions:
            r_partition_name = f'{self.source_table_name}_{partition["suffix"]}'
            msg = (
                f'''Renaming table partition "{self.target_schema}"."{partition['table_name']}"'''
                f' to "{r_partition_name}"'
            )
            LOG.info(msg)
            sql_actions.append(
                f"""
ALTER TABLE "{self.target_schema}"."{partition['table_name']}"
RENAME TO "{r_partition_name}" ;
"""
            )

        LOG.info("Updating recorded partitions")
        update_sql = f"""
UPDATE "{self.target_schema}"."partitioned_tables"
   SET partition_of_table_name = %s
 WHERE partition_of_table_name = %s
   AND schema_name = %s ;
"""
        update_params = [self.source_table_name, self.partitioned_table_name, self.target_schema]

        LOG.info("Executing batch rename commands")
        for sql in sql_actions:
            conn_execute(sql)

        LOG.info("Executing update command")
        conn_execute(update_sql, update_params)

        self.partitioned_table_name = self.source_table_name
        self.source_table_name = f"__{self.source_table_name}"

    def __create_views(self):
        LOG.info("Creating any views")
        for vdef in self.view_iter(self.VIEW_CREATE_ORDER):
            conn_execute(vdef.create())
            if vdef.indexes:
                LOG.info("Creating view indexes")
                for view_ix in vdef.indexes:
                    conn_execute(view_ix.create())
            conn_execute(vdef.alter_owner())

    def __refresh_views(self):
        LOG.info("Refreshing any materialized views")
        for vdef in self.views:
            if vdef.view_type == VIEW_TYPE_MATERIALIZED:
                conn_execute(vdef.refresh())

    def is_partitioned(self, schema_name, table_name):
        """
        Check to see if the specified tabe is a partitioned table
        Args:
            schema_name (str) : Schema name containing the source table
            table_name (str) : Table name
        Returns:
            (bool) : True if partitioned, False if not
        """
        sql = """
select exists (
                select 1
                from pg_partitioned_table
                where partrelid = (
                                    select oid
                                      from pg_class
                                     where relnamespace = %s::regnamespace
                                       and relname = %s
                                  )
              )::boolean as "is_partitioned";
"""
        return conn_execute(sql, (schema_name, table_name)).fetchone()[0]

    def convert_to_partition(self, drop_orig=True):
        """
        Execute the table conversion from the initialized converter
        Params:
            drop_orig (bool) : Flag to drop original objects (default is True)
        """
        with transaction.atomic():
            if self.is_partitioned(self.source_schema, self.source_table_name):
                raise TypeError(
                    f'Source table "{self.source_schema}"."{self.source_table_name}" is already partitioned'
                )

        # Create structures
        with transaction.atomic():
            self.__create_table_like_source()
            self.__set_primary_key()
            self.__set_column_definitions()
            self.__set_constraints()
            self.__create_indexes()
            if self.__new_trigger:
                self.__create_default_partition_new()
                self.__create_partitions_new()
            else:
                self.__create_default_partition()
                self.__create_partitions()

        # Copy all source data
        with transaction.atomic():
            self.__copy_data()

        # Rename objects (acquires lock)
        with transaction.atomic():
            if self.__new_trigger:
                self.__rename_objects_new()
            else:
                self.__rename_objects()

        # Create views
        with transaction.atomic():
            self.__create_views()
            self.__refresh_views()

        # Truncate and drop original objects
        if drop_orig:
            with transaction.atomic():
                self.drop_original_objects()

    def drop_original_objects(self):
        """
        Truncate and drop source table and its dependents.
        """
        sql = f"""
TRUNCATE TABLE "{self.source_schema}"."{self.source_table_name}" ;
"""
        conn_execute(sql)
        sql = f"""
DROP TABLE "{self.source_schema}"."{self.source_table_name}" CASCADE ;
"""
        conn_execute(sql)


# ====================================================================
#  Functionality to move data from default partitions to new partitions
# ====================================================================
class PartitionDefaultData:
    """
    Move data from a specified default partition into newly-created month range partitions
    Params:
        conn : database connection (If None, then gets the connection)
        schema_name (str) : Schema containing the partitioned data and tracking table
        partitioned_table (str) : Partitioned table name
        partitioned_table (str) : Default partition table name
    """

    # NOTE: This needs to be updated to support subpartitions

    def __init__(self, schema_name, partitioned_table, default_partition=None):
        self.conn = transaction.get_connection()
        self.schema_name = schema_name
        self.partitioned_table = partitioned_table
        self.default_partition = default_partition or self._get_default_partition()
        self.partition_name = ""
        self.tracking_rec = None
        self.tx_id = str(uuid.uuid4()).replace("-", "_")
        self._get_default_partition_tracker_info()

    def _get_default_partition(self):
        sql = """
SELECT d.relname::text as "table_name"
  FROM pg_partitioned_table pt
  JOIN pg_class c
    ON c.oid = pt.partrelid
  JOIN pg_namespace n
    ON n.oid = c.relnamespace
  JOIN pg_class d
    ON d.oid = pt.partdefid
 WHERE n.nspname = %s::name
   AND c.relname = %s::name;
"""
        cur = conn_execute(sql, (self.schema_name, self.partitioned_table))
        res = fetchone(cur)["table_name"]

        return res

    def _get_default_partition_tracker_info(self):
        sql = f"""
SELECT *
  FROM "{self.schema_name}"."partitioned_tables"
 WHERE schema_name = %s
   AND partition_of_table_name = %s
   AND table_name = %s
   AND partition_parameters->>'default' = 'true'
"""
        LOG.info(f"Getting default tracker record for {self.default_partition} of {self.partitioned_table}")
        cur = conn_execute(sql, (self.schema_name, self.partitioned_table, self.default_partition), _conn=self.conn)
        self.tracking_rec = fetchone(cur)
        self.tracking_rec["partition_parameters"] = json.loads(self.tracking_rec["partition_parameters"])
        self.partition_type = self.tracking_rec["partition_type"]
        self.partition_key = self.tracking_rec["partition_col"]

    def _update_partition_tracking_record(self):
        LOG.debug("Execute SQL to update partition tracking record")
        update_sql = f"""
UPDATE "{self.schema_name}"."partitioned_tables"
   SET "schema_name" = %(schema_name)s ,
       "table_name" = %(table_name)s ,
       "partition_of_table_name" = %(partition_of_table_name)s ,
       "partition_type" = %(partition_type)s ,
       "partition_col" = %(partition_col)s ,
       "partition_parameters" = %(partition_parameters_str)s ,
       "active" = %(active)s
 WHERE "id" = %(id)s;
"""
        self.tracking_rec["partition_parameters"]["from"] = str(self.tracking_rec["partition_parameters"]["from"])
        self.tracking_rec["partition_parameters"]["to"] = str(self.tracking_rec["partition_parameters"]["to"])
        self.tracking_rec["partition_parameters_str"] = json.dumps(self.tracking_rec["partition_parameters"])
        conn_execute(update_sql, self.tracking_rec, _conn=self.conn)

    def _create_partititon_tracking_record(self):
        LOG.debug(f"Creating tracking record for new partition {self.partition_name}")
        self.tracking_rec["partition_parameters"]["from"] = str(self.tracking_rec["partition_parameters"]["from"])
        self.tracking_rec["partition_parameters"]["to"] = str(self.tracking_rec["partition_parameters"]["to"])
        self.tracking_rec["partition_parameters"]["default"] = False
        self.tracking_rec["partition_parameters_str"] = json.dumps(self.tracking_rec["partition_parameters"])
        part_track_insert_sql = f"""
INSERT INTO "{self.schema_name}"."partitioned_tables"
       (schema_name, table_name, partition_of_table_name, partition_type, partition_col, partition_parameters, active)
VALUES (%(schema_name)s, %(table_name)s, %(partition_of_table_name)s, %(partition_type)s, %(partition_col)s,
        %(partition_parameters_str)s::jsonb, true)
RETURNING *;
"""
        cur = conn_execute(part_track_insert_sql, self.tracking_rec, _conn=self.conn)
        self.tracking_rec = fetchone(cur)
        self.tracking_rec["partition_parameters_str"] = None
        self.tracking_rec["partition_parameters"] = json.loads(self.tracking_rec["partition_parameters"])

    def _create_partition(self):
        self._create_partititon_tracking_record()

    def _attach_partition(self):
        self.tracking_rec["active"] = True
        LOG.debug("Updating tracking active state")
        self._update_partition_tracking_record()

    def _detach_partition(self):
        self.tracking_rec["active"] = False
        LOG.debug("Updating tracking active state")
        self._update_partition_tracking_record()

    def _get_new_partitions_from_default(self):
        partition_start_sql = f"""
SELECT DISTINCT
       date_trunc('month', usage_start)::date as "partition_start",
       date_trunc('month', (date_trunc('month', usage_start) + '1 month'::interval))::date as "partition_end"
  FROM "{self.schema_name}"."{self.default_partition}"
 ORDER
    BY 1;
"""
        LOG.info(f'Getting partition bounds for data in "{self.schema_name}"."{self.default_partition}"')
        cur = conn_execute(partition_start_sql)
        res = [(r["partition_start"], r["partition_end"]) for r in fetchall(cur)]

        if len(res) == 0:
            LOG.info("Nothing to do")

        return res

    def repartition_default_data(self):
        # NOTE: This needs to be updated to be more generic
        new_partitions = self._get_new_partitions_from_default()
        if new_partitions:
            mv_recs_sql = f"""
WITH __mv_recs_{self.tx_id} as (
DELETE
  FROM "{self.schema_name}"."{self.default_partition}"
 WHERE usage_start >= %s
   AND usage_start < %s
RETURNING *
)
INSERT INTO {{}}
SELECT * FROM __mv_recs_{self.tx_id} ;
"""

            for bounds in new_partitions:
                p_from, p_to = bounds
                self.tracking_rec["table_name"] = f"{self.partitioned_table}_{p_from.strftime('%Y_%m')}"
                full_partition_name = f'''"{self.schema_name}"."{self.tracking_rec['table_name']}"'''

                # A little jiggery-pokery here to increase efficiency.
                # The partition is named properly, but it set as a partition for 100 years in the future
                # This will allow us to create the partition with all of the structure that is required.
                # Before the data move, we will detach the partition, then move the data,
                # then reattach with the proper bounds.
                self.tracking_rec["partition_parameters"]["from"] = p_from.replace(year=p_from.year + 100)
                self.tracking_rec["partition_parameters"]["to"] = p_to.replace(year=p_to.year + 100)

                LOG.info(
                    f"Re-partitioning {self.schema_name}.{self.default_partition} into {full_partition_name} "
                    + f"for {self.partition_key} values from {p_from} to {p_to}"
                )
                with transaction.atomic():
                    # Create new partition
                    self._create_partition()
                    # Detach it so we can move the data
                    self._detach_partition()

                    # Move data into new partition
                    conn_execute(mv_recs_sql.format(full_partition_name), (p_from, p_to), _conn=self.conn)

                    # Re-attach partition with actual bounds
                    self.tracking_rec["partition_parameters"]["from"] = p_from
                    self.tracking_rec["partition_parameters"]["to"] = p_to
                    self._attach_partition()


def get_partitioned_tables_with_default(schema_name=None, partitioned_table_name=None):
    default_partition_sql = """
SELECT dp.relnamespace::regnamespace::text as "schema_name",
       dp.relname::text as "default_partition",
       pt.relname::text as "partitioned_table"
  FROM pg_partitioned_table ptr
  JOIN pg_class dp
    ON dp.oid = ptr.partdefid
  JOIN pg_class pt
    ON pt.oid = ptr.partrelid
       /* must actually be a namespace */
  JOIN pg_namespace n
    ON n.oid = dp.relnamespace
       /* must be constrained to app tenant schemas */
  JOIN public.api_tenant ten
    ON ten.schema_name = n.nspname
 WHERE n.nspname != %s::name  -- do not execute against template schema
   AND n.nspname = coalesce(%s::name, n.nspname)
   AND pt.relname = coalesce(%s::name, pt.relname)
 ORDER
    BY 1, 2;
"""
    cur = conn_execute(default_partition_sql, (_TEMPLATE_SCHEMA, schema_name, partitioned_table_name))
    default_partitions = fetchall(cur)

    return default_partitions


# This is a crawler interface to the PartitionDefaultData class
def repartition_default_data(schema_name=None, partitioned_table_name=None):
    """
    Move any data in a default partition to the requisite partition.
    Unless constrained to a schema or table, it will crawl over all schemata and default table partitions
    Params:
        schema_name (str) : Constrain to specified schema
        partitioned_table_name (str) : Constrain to specified partitioned table
    """
    default_partitions = get_partitioned_tables_with_default(schema_name, partitioned_table_name)

    for default_rec in default_partitions:
        default_partitioner = PartitionDefaultData(
            default_rec["schema_name"],
            default_rec["partitioned_table"],
            default_partition=default_rec["default_partition"],
        )
        default_partitioner.repartition_default_data()


def _get_or_create_default_partition(part_rec):
    """
    Use the specified record to return an existing or newly-created default partition

    Params:
        part_rec (dict) : A dict describing a partitioned_tables record.

    Returns: (tuple)
        (PartitionedTable instance, created boolean)
    """
    default_keys = ("schema_name", "table_name", "partition_of_table_name", "partition_type", "partition_col")
    default_params = {k: v for k, v in part_rec.items() if k in default_keys}
    default_params["table_name"] = f"{default_params['partition_of_table_name']}_default"
    default_params["partition_parameters"] = {"default": True}
    default_part, created = PartitionedTable.objects.get_or_create(
        schema_name=default_params["schema_name"],
        table_name=default_params["table_name"],
        partition_of_table_name=default_params["partition_of_table_name"],
        partition_parameters__default=True,
        defaults=default_params,
    )

    LOG.info(f"{'Created' if created else 'Retrieved'} default partition {default_part.table_name}")

    return default_part, created


def _check_default_partition_data(default_partition, part_rec):
    """
    Use the specified record to check if the default partition contains data
    for the parameters defined in the partition record. If it detects data, the partition parameters
    will be altered to be some time in the future for a range or a ramdom array of letters for a list.
    The original parameters will be returned if this is the case. Also returned will be the
    SQL where clause needed to check the conditions. This will be re-used when moving data.

    Params:
        default_partition (PartitionedTable) : The tracking record for the default partition
        part_rec (dict) : A dict describing a partitioned_tables record.

    Returns: (tuple)
        (dict, str):
            dict : The original partition parameters or empty dict
            str : The SQL where clause (minus "where") for the needed conditions when moving data
    """
    params = None
    if default_partition.partition_type == default_partition.RANGE:
        chk_where = f'"{default_partition.partition_col}" >= %s AND "{default_partition.partition_col}" < %s'
        params = [part_rec["partition_parameters"]["from"], part_rec["partition_parameters"]["to"]]
    else:
        chk_where = f'"{default_partition.partition_col}" IN ( %s )'
        params = [part_rec["partition_parameters"]["in"]]

    with transaction.get_connection().cursor() as cur:
        chk_where = cur.mogrify(chk_where, params).decode("utf-8")

    chk_sql = f"""
SELECT EXISTS (
    SELECT 1
      FROM "{default_partition.schema_name}"."{default_partition.table_name}"
     WHERE {chk_where}
);
"""
    with transaction.get_connection().cursor() as cur:
        cur.execute(chk_sql)
        res = cur.fetchone()

    if res[0]:
        LOG.info(f"Overlapping data found in the default partition for {chk_where}")
        restore = part_rec["partition_parameters"].copy()
        if default_partition.partition_type == default_partition.RANGE:
            pp_from = ciso8601.parse_datetime(part_rec["partition_parameters"]["from"]).date()
            pp_to = ciso8601.parse_datetime(part_rec["partition_parameters"]["to"]).date()
            delta = relativedelta(years=random.randrange(100, 7000))
            part_rec["partition_parameters"]["from"] = str(pp_from + delta)
            part_rec["partition_parameters"]["to"] = str(pp_to + delta)
        else:
            pp_in = []
            for _ in range(10):
                pp_in.append(f"'{random.choice(string.ascii_letters)}'")
            part_rec["partition_parameters"]["in"] = ",".join(pp_in)
    else:
        LOG.info("No overlapping data in the default partition")
        restore = {}

    return restore, chk_where


def _move_partition_data(target_partition, source_partition, conditions):
    """
    Move data matching conditions from the source partition to the target partition.

    Params:
        target_partition (PartitionTable) : The target partition tracking record
        source_partition (PartitionTable) : The source partition tracking record
        conditions (str) : SQL where clause conditions

    Returns: tuple(cp_recs int, dl_recs int)
        cp_recs : number of records copied
        dl_recs : number of records deleted
    """
    mv_sql = f"""
INSERT INTO "{target_partition.schema_name}"."{target_partition.table_name}"
SELECT *
  FROM "{source_partition.schema_name}"."{source_partition.table_name}"
 WHERE {conditions} ;
"""
    dl_sql = f"""
DELETE
  FROM "{source_partition.schema_name}"."{source_partition.table_name}"
 WHERE {conditions} ;
"""
    cp_recs = dl_recs = 0
    with transaction.get_connection().cursor() as cur:
        LOG.info(f"Copy data from {source_partition.table_name} to {target_partition.table_name} where {conditions}")
        cur.execute(mv_sql)
        cp_recs = cur.rowcount
        LOG.info(f"Copied {cp_recs} records")
        LOG.info(f"Delete data from {source_partition.table_name} where {conditions}")
        cur.execute(dl_sql)
        dl_recs = cur.rowcount
        LOG.info(f"Deleted {dl_recs} records")

    return (cp_recs, dl_recs)


def get_or_create_partition(part_rec, _default_partition=None):
    """
    Get or create an existing partition.
    Creating:
        1.  The default partition tracking record will be retrieved or created
        2.  The default partition will be checked to see if it contains data that
            overlaps with the constraint on the new partition. If so, the data
            in the default partition will be moved to the new partition.

    Params:
        part_rec (dict) :   A dict desrribing a partition record.
                            If the record needs to be created ALL fields to support that record
                            MUST be provided.

    Returns: tuple(partition, created)
        partition (PartitionTable) : The tracking record for the found or created partition
        created (boolean) : Flag indicating that the record was created (True) or retrieved (False).
    """
    if "id" in part_rec:
        del part_rec["id"]
    if isinstance(part_rec.get("partition_parameters", {}).get("from"), datetime.datetime):
        part_rec["partition_parameters"]["from"] = str(part_rec["partition_parameters"]["from"].date())
    elif isinstance(part_rec.get("partition_parameters", {}).get("from"), datetime.date):
        part_rec["partition_parameters"]["from"] = str(part_rec["partition_parameters"]["from"])
    if isinstance(part_rec.get("partition_parameters", {}).get("to"), datetime.datetime):
        part_rec["partition_parameters"]["to"] = str(part_rec["partition_parameters"]["to"].date())
    elif isinstance(part_rec.get("partition_parameters", {}).get("to"), datetime.date):
        part_rec["partition_parameters"]["to"] = str(part_rec["partition_parameters"]["to"])

    with schema_context(part_rec["schema_name"]):
        # Find or create the default partition
        if _default_partition:
            default_partition, default_created = _default_partition, False
        else:
            default_partition, default_created = _get_or_create_default_partition(part_rec)

        if part_rec.get("partition_parameters", {}).get("default") or "default" in part_rec.get("table_name"):
            return default_partition, default_created

        if not default_created:
            restore_partition_parameters, conditions = _check_default_partition_data(default_partition, part_rec)
        else:
            restore_partition_parameters = {}

        partition, created = PartitionedTable.objects.get_or_create(
            schema_name=part_rec["schema_name"],
            table_name=part_rec["table_name"],
            partition_of_table_name=part_rec["partition_of_table_name"],
            defaults=part_rec,
        )
        LOG.info(f'{"Created" if created else "Retrieved"} partition "{partition.table_name}"')

        if created and restore_partition_parameters:
            # Detach the partition (uses trigger)
            LOG.info(f'Detaching partition "{partition.table_name}" for data move')
            partition.active = False
            partition.save()
            # Move data from the default partition to the detached partition
            LOG.info(f'Executing data move from default partition to "{partition.table_name}"')
            _move_partition_data(partition, default_partition, conditions)
            # Re-attach the partition with the original parameters (uses trigger)
            LOG.info(f'Reattach partition "{partition.table_name}"')
            partition.partition_parameters = restore_partition_parameters
            partition.active = True
            partition.save()

    return partition, created


class PartitionHandlerMixin:
    def _handle_partitions(self, schema_name, table_names, start_date, end_date):  # noqas: C901
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        elif isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()
        elif isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()
        if isinstance(table_names, str):
            table_names = [table_names]

        for table_name in table_names:
            default_part = PartitionedTable.objects.filter(
                schema_name=schema_name,
                partition_of_table_name=table_name,
                partition_type=PartitionedTable.RANGE,
                partition_parameters__default=True,
            ).first()
            if default_part:
                partition_start = start_date.replace(day=1)
                month_interval = relativedelta(months=1)
                needed_partition = None
                partition_col = default_part.partition_col
                newpart_vals = dict(
                    schema_name=schema_name,
                    table_name=None,
                    partition_of_table_name=table_name,
                    partition_type=PartitionedTable.RANGE,
                    partition_col=partition_col,
                    partition_parameters={"default": False, "from": None, "to": None},
                    active=True,
                )
                for _ in range(relativedelta(end_date.replace(day=1), partition_start).months + 1):
                    if needed_partition is None:
                        needed_partition = partition_start
                    else:
                        needed_partition = needed_partition + month_interval

                    partition_name = f"{table_name}_{needed_partition.strftime('%Y_%m')}"
                    newpart_vals["table_name"] = partition_name
                    newpart_vals["partition_parameters"]["from"] = str(needed_partition)
                    newpart_vals["partition_parameters"]["to"] = str(needed_partition + month_interval)
                    # Successfully creating a new record will also create the partition
                    newpart, created = get_or_create_partition(newpart_vals, _default_partition=default_part)
                    LOG.debug(f"partition = {newpart}")
                    LOG.debug(f"created = {created}")
                    if created:
                        LOG.info(f"Created partition {newpart.schema_name}.{newpart.table_name}")
