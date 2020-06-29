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
import logging
import re

from django.db import connection as conn
from django.db import transaction

CURRENT_SCHEMA = "current_schema"
BIGINT = "bigint"
INT = "int"

PARTITION_RANGE = "RANGE"
PARTITION_LIST = "LIST"

VIEW_TYPE_MATERIALIZED = "m"

LOG = logging.getLogger(__file__)


def conn_execute(sql, params=None):
    if sql:
        cursor = conn.cursor()
        LOG.debug(f"SQL: {sql}")
        LOG.debug(f"PARAMS: {params}")
        cursor.execute(sql, params)
        return cursor
    else:
        return None


def fetchall(cursor):
    if cursor:
        cursor_def = [d.name for d in cursor.description]
        return [dict(zip(cursor_def, r)) for r in cursor.fetchall()]
    else:
        return []


def fetchone(cursor):
    if cursor:
        return dict(zip((d.name for d in cursor.description), cursor.fetchone()))
    else:
        return {}


def resolve_schema(schema):
    if schema == CURRENT_SCHEMA:
        cur = conn_execute('select current_schema as "current_schema";')
        schema = cur.fetchone()[0]

    LOG.info(f"Resolve schema is {schema}")
    return schema


class Default:
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


class SequenceDefinition:
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
        self.target_schema = target_schema
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
        self.cycle = "CYCLE" if rec["cycle"] else "NO CYCLE"
        self.current_value = rec["last_value"]
        self.owner = rec["sequenceowner"]

    def default_constraint(self):
        return f"nextval('{self.name}'::regclass)"

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
                (self.current_value, self.current_value),
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
    def __init__(self, target_schema, target_table, column_name, data_type=None, using=None, null=None, default=None):
        self.target_schema = target_schema
        self.target_table = target_table
        self.column_name = column_name
        self.data_type = data_type
        self.using = using
        self.null = null
        self.default = default

    def alter_column(self):
        LOG.info("Running alter column")
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
            alters.append(
                f"""      ALTER COLUMN "{self.column_name}" SET DEFAULT {self.default}
"""
            )
        sql += ", ".join(alters) + ";"
        return sql


class ConstraintDefinition:
    def __init__(self, target_schema, target_table, constraintrec):
        self.target_schema = target_schema
        self.target_table = target_table
        self.constraint_name = constraintrec["constraint_name"]
        self.definition = constraintrec["definition"]

    def alter_add_constraint(self):
        LOG.info("Runing ALTER TABLE ADD CONSTRAINT")
        sql = f"""
ALTER TABLE "{self.target_schema}"."{self.target_table}"
      ADD CONSTRAINT "p_{self.constraint_name}" {self.definition} ;
"""
        return sql


class PKDefinition:
    def __init__(self, name, column_names):
        self.column_names = column_names
        self.name = name

    def alter_table(self, schema_name, table_name):
        LOG.info("Adding PRIMARY KEY constraint")
        return f"""
ALTER TABLE "{schema_name}"."{table_name}"
      ADD CONSTRAINT "{self.name}"
      PRIMARY KEY ({",".join("{c.name}" for c in self.column_names)}) ;
"""


class IndexDefinition:
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
        LOG.info(f'Creating index "p_{self.index_name}"')
        index_parts = self.INDEX_PARSER.findall(self.definition)
        if index_parts:
            index_parts = list(index_parts[0])
            index_parts[self.INDEX_NAME_IX] = f"p_{self.index_name}"
            index_parts[self.INDEX_TABLE_IX] = f"{self.target_schema}.{self.target_table}"
            return " ".join(index_parts)

        return ""


class ViewDefinition:
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
    def __init__(
        self,
        source_table_name,
        partition_key,
        partition_type,
        pk_def=None,
        col_def=[],
        target_schema=CURRENT_SCHEMA,
        source_schema=CURRENT_SCHEMA,
    ):
        self.conn = conn
        self.target_schema = resolve_schema(target_schema)
        self.partitioned_table_name = "p_" + source_table_name
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
        LOG.debug(f"Getting constraints for table {self.source_schema}.{self.source_table_name}")
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
        LOG.debug(f"Getting indexes for table {self.source_schema}.{self.source_table_name}")
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
        LOG.debug(f"Getting views referencing table {self.source_schema}.{self.source_table_name}")
        sql = """
WITH RECURSIVE view_deps AS (
SELECT DISTINCT
       dependent_ns.nspname as dependent_schema,
       dependent_view.oid as dependent_view_oid,
       dependent_view.relname as dependent_view,
       dependent_view.relkind as dependent_view_type,
       dependent_view_owner.rolname as dependent_view_owner,
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
  JOIN pg_authid dependent_view_owner
    ON dependent_view_owner.oid = dependent_view.relowner
 WHERE NOT (dependent_ns.nspname = source_ns.nspname AND
            dependent_view.relname = source_table.relname)
   AND source_table.relnamespace = %s::regnamespace
   AND source_table.oid = %s::regclass
UNION
SELECT DISTINCT
       dependent_ns.nspname as dependent_schema,
       dependent_view.oid as dependent_view_oid,
       dependent_view.relname as dependent_view,
       dependent_view.relkind as dependent_view_type,
       dependent_view_owner.rolname as dependent_view_owner,
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
  JOIN pg_authid dependent_view_owner
    ON dependent_view_owner.oid = dependent_view.relowner
  JOIN view_deps vd
    ON vd.dependent_schema = source_ns.nspname
   AND vd.dependent_view = source_table.relname
   AND NOT (dependent_ns.nspname = vd.dependent_schema AND
            dependent_view.relname = vd.dependent_view)
)
SELECT vd.*,
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
        LOG.info(f'Creating default partition "{self.target_schema}"."{self.partitioned_table_name}_default"')
        sql = f"""
CREATE TABLE "{self.target_schema}"."{self.source_table_name}_default"
PARTITION OF {self.partitioned_table_name} DEFAULT ;
"""
        conn_execute(sql)

        LOG.debug("Recording default partition")
        # TODO: Utilize model
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
        params = [
            self.target_schema,
            f"{self.partitioned_table_name}_default",
            self.partitioned_table_name,
            self.partition_type.lower(),
            self.partition_key,
            '{"default": true}',
        ]
        conn_execute(sql, params)

    def __set_primary_key(self):
        LOG.info("Setting any primary key definition")
        if self.pk_def:
            self.pk_def.alter_table(self.target_schema, self.partitioned_table_name)

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
        LOG.info("Applying any table indexes")
        for idef in self.indexes:
            conn_execute(idef.create())

    def __create_partitions(self):
        sql = """
CALL public.create_date_partitions( %s, %s, %s, %s, %s );
"""
        params = [
            f"{self.source_schema}.{self.source_table_name}",  # This will be quoted properly in the proc
            self.partition_key,
            self.target_schema,
            self.partitioned_table_name,
            self.partition_key,
        ]
        conn_execute(sql, params)

    def __copy_data(self):
        sql = f"""
INSERT INTO "{self.target_schema}"."{self.partitioned_table_name}"
SELECT * FROM "{self.source_schema}"."{self.source_table_name}" ;
"""
        with transaction.atomic():
            conn_execute(sql)

    def __rename_objects(self):
        sql_actions = [
            f"""
LOCK TABLE "{self.source_schema}"."{self.source_table_name}" ;
"""
        ]
        for vdef in self.views:
            sql_actions.extend(vdef.rename_original_view_indexes())
            sql_actions.append(vdef.rename_original_view())

        sql_actions.append(
            f"""
ALTER TABLE "{self.source_schema}"."{self.source_table_name}"
RENAME TO "__{self.source_table_name}" ;
"""
        )
        sql_actions.append(
            f"""
ALTER TABLE "{self.target_schema}"."{self.partitioned_table_name}"
RENAME TO "{self.source_table_name}" ;
"""
        )
        update_sql = """
UPDATE partitioned_tables
   SET partition_of_table_name = %s
 WHERE partition_of_table_name = %s
   AND schema_name = %s ;
"""
        update_params = [self.source_table_name, self.partitioned_table_name, self.target_schema]

        for sql in sql_actions:
            conn_execute(sql)

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
            if vdef.view_type == "matview":
                conn_execute(vdef.refresh())

    def convert_to_partition(self, drop_orig=True):
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
        sql = f"""
TRUNCATE TABLE "{self.source_schema}"."{self.source_table_name}" ;
"""
        conn_execute(sql)
        sql = f"""
DROP TABLE "{self.source_schema}"."{self.source_table_name}" CASCADE ;
"""
        conn_execute(sql)
