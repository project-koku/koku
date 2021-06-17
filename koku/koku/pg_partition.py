#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import logging
import os
import re
import uuid

import ciso8601
from dateutil.relativedelta import relativedelta
from django.db import connection as conn
from django.db import transaction


# If this is detected, the code will try to resolve this to a name
# because, in some functionality, this needs to be a string vs the
# keyword.
CURRENT_SCHEMA = "current_schema"
BIGINT = "bigint"
INT = "int"

PARTITION_RANGE = "RANGE"
PARTITION_LIST = "LIST"

# This value from pg_class.relkind denotes a materialized view
VIEW_TYPE_MATERIALIZED = "m"

LOG = logging.getLogger("pg_partition")
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
        LOG.info(f"SQL: {cursor.mogrify(sql, params).decode('utf-8')}")
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
        self.owner = rec["sequenceowner"]

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
        self.index_name = indexrec["indexname"]
        self.definition = indexrec["indexdef"]

        if ";" not in self.definition[:-10]:
            self.definition += " ;"

    def create(self):
        index_parts = self.INDEX_PARSER.findall(self.definition)
        if index_parts:
            LOG.info(f'Creating index "p_{self.index_name}"')
            index_parts = list(index_parts[0])
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
        self.schema_name = viewrec["source_schema"]
        self.table_name = viewrec["source_table"]
        self.view_schema = viewrec["dependent_schema"]
        self.view_name = viewrec["dependent_view"]
        self.view_type = viewrec["dependent_view_type"]
        self.definition = viewrec["definition"]
        self.view_owner = viewrec["dependent_view_owner"]
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
        view_type = "MATERIALIZED" if self.view_type == VIEW_TYPE_MATERIALIZED else ""
        LOG.info(f'Creating {view_type} view "{self.view_name}')
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

    def __repr__(self):
        return f"""Convert "{self.source_schema}"."{self.source_table_name}" to a partitioned table"""

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
 where n.nspname = %s
   and t.relname = %s
   and t.relkind = 'r'
)
select i.*
  from pg_indexes i
 where i.schemaname = %s
   and i.tablename = %s
   and not exists (select 1 from pk_indexes x where i.indexname = x.relname)
 order
    by i.tablename;
"""
        params = [self.source_schema, self.source_table_name, self.source_schema, self.source_table_name]
        cur = conn_execute(sql, params)
        return [IndexDefinition(self.target_schema, self.partitioned_table_name, rec) for rec in fetchall(cur)]

    def __get_views(self):
        LOG.info(f"Getting views referencing table {self.source_schema}.{self.source_table_name}")
        sql = """
WITH RECURSIVE view_deps AS (
SELECT DISTINCT
       dependent_ns.nspname as dependent_schema,
       dependent_view.oid as dependent_view_oid,
       dependent_view.relname as dependent_view,
       dependent_view.relkind as dependent_view_type,
       dependent_view.relowner::regrole::text as dependent_view_owner,
       source_ns.nspname as source_schema,
       source_table.relname as source_table
  FROM pg_depend
  JOIN pg_rewrite
    ON pg_depend.objid = pg_rewrite.oid
  JOIN pg_class as dependent_view
    ON pg_rewrite.ev_class = dependent_view.oid
  JOIN pg_class as source_table
    ON pg_depend.refobjid = source_table.oid
  JOIN pg_namespace dependent_ns
    ON dependent_ns.oid = dependent_view.relnamespace
  JOIN pg_namespace source_ns
    ON source_ns.oid = source_table.relnamespace
 WHERE NOT (dependent_ns.nspname = source_ns.nspname AND
            dependent_view.relname = source_table.relname)
   AND source_table.relnamespace = %s::regnamespace
   AND source_table.relname = %s
UNION
SELECT DISTINCT
       dependent_ns.nspname as dependent_schema,
       dependent_view.oid as dependent_view_oid,
       dependent_view.relname as dependent_view,
       dependent_view.relkind as dependent_view_type,
       dependent_view.relowner::regrole::text as dependent_view_owner,
       source_ns.nspname as source_schema,
       source_table.relname as source_table
  FROM pg_depend
  JOIN pg_rewrite
    ON pg_depend.objid = pg_rewrite.oid
  JOIN pg_class as dependent_view
    ON pg_rewrite.ev_class = dependent_view.oid
  JOIN pg_class as source_table
    ON pg_depend.refobjid = source_table.oid
  JOIN pg_namespace dependent_ns
    ON dependent_ns.oid = dependent_view.relnamespace
  JOIN pg_namespace source_ns
    ON source_ns.oid = source_table.relnamespace
  JOIN view_deps vd
    ON vd.dependent_schema = source_ns.nspname
   AND vd.dependent_view = source_table.relname
   AND NOT (dependent_ns.nspname = vd.dependent_schema AND
            dependent_view.relname = vd.dependent_view)
)
SELECT vd.dependent_schema,
       vd.dependent_view_oid,
       vd.dependent_view,
       vd.dependent_view_type,
       replace(vd.dependent_view_owner, '"', '') as dependent_view_owner,
       vd.source_schema,
       vd.source_table,
       (select array_agg(row_to_json(vi))
          from pg_indexes vi
         where vi.schemaname = vd.dependent_schema
           and vi.tablename = vd.dependent_view)::json[] as indexes,
       pg_get_viewdef(dependent_view_oid) as definition
  FROM view_deps vd
 ORDER BY source_schema, source_table;
"""
        cur = conn_execute(sql, [self.source_schema, self.source_table_name])
        return [ViewDefinition(self.target_schema, rec) for rec in fetchall(cur)]

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
            conn_execute(cdef.alter_add_constraint())

    def __create_indexes(self):
        for idef in self.indexes:
            LOG.info(f"Applying index definition from {idef.index_name}")
            conn_execute(idef.create())

    def __create_partitions(self):
        # Get "requested" partitions
        sql = """
select partition_start from scan_for_date_partitions(%s::text, %s::text, %s::text, %s::text);
"""
        params = [
            f"{self.source_schema}.{self.source_table_name}",  # This will be quoted properly in the proc
            self.partition_key,
            self.target_schema,
            self.partitioned_table_name,
        ]
        cur = conn_execute(sql, params)
        requested_partitions = fetchall(cur)

        # Get existing partitions except the default partition
        sql = f"""
select (partition_parameters->>'from')::date as existing_partition
  from "{self.target_schema}"."partitioned_tables"
 where schema_name = %s
   and partition_of_table_name = %s
   and table_name ~ %s
   and partition_parameters->>'default' = 'false';
"""
        params = [self.target_schema, self.partitioned_table_name, f"^{self.partitioned_table_name}"]
        cur = conn_execute(sql, params)
        existing_partitions = fetchall(cur)

        needed_partitions = {p["partition_start"] for p in requested_partitions} - {
            ciso8601.parse_datetime(p["partition_parameters"]["from"]).date() for p in existing_partitions
        }

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
        for vdef in self.views:
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
            self.__create_default_partition()
            self.__create_partitions()

        # Copy all source data
        with transaction.atomic():
            self.__copy_data()

        # Rename objects (acquires lock)
        with transaction.atomic():
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

    def __init__(self, schema_name, partitioned_table, default_partition=None):
        self.conn = transaction.get_connection()
        self.schema_name = schema_name
        self.partitioned_table = partitioned_table
        self.default_partition = default_partition or self._get_default_partition()
        self.partition_name = ""
        self.tracking_rec = None
        self.partition_parameters = {}
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
        default_tracker = fetchone(cur)
        self.partition_type = default_tracker["partition_type"]
        self.partition_key = default_tracker["partition_col"]

    def _update_partition_tracking_record(self, set_col):
        LOG.debug(f"Execute SQL to update partition_parameters.{set_col}")
        if set_col == "partition_parameters":
            partition_parameters = self.partition_parameters.copy()
            partition_parameters["from"] = str(partition_parameters["from"])
            partition_parameters["to"] = str(partition_parameters["to"])
            partition_parameters["default"] = False
            self.tracking_rec["partition_parameters"] = json.dumps(partition_parameters)

        update_sql = f"""
UPDATE "{self.schema_name}"."partitioned_tables"
   SET {set_col} = %s{'::boolean' if set_col == 'active' else '::jsonb'}
 WHERE "id" = %s;
"""
        vals = [self.tracking_rec[set_col], self.tracking_rec["id"]]

        conn_execute(update_sql, vals, _conn=self.conn)

    def _create_partititon_tracking_record(self):
        LOG.debug(f"Creating tracking record for new partition {self.partition_name}")
        partition_parameters = self.partition_parameters.copy()
        partition_parameters["from"] = str(partition_parameters["from"])
        partition_parameters["to"] = str(partition_parameters["to"])
        partition_parameters["default"] = False
        part_track_insert_sql = f"""
INSERT INTO "{self.schema_name}"."partitioned_tables"
       (schema_name, table_name, partition_of_table_name, partition_type, partition_col, partition_parameters, active)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, true)
RETURNING *;
"""
        vals = (
            self.schema_name,
            self.partition_name,
            self.partitioned_table,
            self.partition_type,
            self.partition_key,
            json.dumps(partition_parameters),
        )
        cur = conn_execute(part_track_insert_sql, vals, _conn=self.conn)
        self.tracking_rec = fetchone(cur)

    def _create_partition(self):
        self._create_partititon_tracking_record()

    def _attach_partition(self):
        self.tracking_rec["active"] = True

        # This is necessary to prevent two triggers from firing and getting a race condition
        LOG.debug("Updating tracking partition parameters")
        self._update_partition_tracking_record(set_col="partition_parameters")
        LOG.debug("Updating tracking active state")
        self._update_partition_tracking_record(set_col="active")

    def _detach_partition(self):
        self.tracking_rec["active"] = False
        self._update_partition_tracking_record(set_col="active")

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
                self.partition_name = f"{self.partitioned_table}_{p_from.strftime('%Y_%m')}"
                full_partition_name = f'"{self.schema_name}"."{self.partition_name}"'

                # A little jiggery-pokery here to increase efficiency.
                # The partition is named properly, but it set as a partition for 100 years in the future
                # This will allow us to create the partition with all of the structure that is required.
                # Before the data move, we will detach the partition, then move the data,
                # then reattach with the proper bounds.
                self.partition_parameters = {
                    "from": p_from.replace(year=p_from.year + 100),
                    "to": p_to.replace(year=p_to.year + 100),
                }

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
                    self.partition_parameters["from"] = p_from
                    self.partition_parameters["to"] = p_to
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
