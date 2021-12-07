#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
import uuid

from django.db import connection as conn
from tenant_schemas.utils import schema_context

from . import pg_partition as ppart
from api.iam.test.iam_test_case import IamTestCase
from reporting.models import AWSCostEntryLineItemDailySummary
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import PartitionedTable


def _execute(sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _get_table_partition_info(schema, table):
    sql = """
select c.relkind,
       c.relispartition
  from pg_class c
  join pg_namespace n
    on n.oid = c.relnamespace
 where n.nspname = %s
   and c.relname = %s ;
"""
    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        res = cur.fetchone()

    return dict(zip(("relkind", "relispartition"), res)) if res else res


class TestGoCPartition(IamTestCase):
    PARTITIONED_TABLE_NAME = "__pg_partition_test2"
    SCHEMA_NAME = "acct10001"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sql = f"""
create table if not exists {cls.SCHEMA_NAME}.{cls.PARTITIONED_TABLE_NAME} (
    id bigserial,
    ref_id int,
    utilization_date date not null,
    label text not null,
    data numeric(15,4),
    primary key (utilization_date, id)
)
partition by range (utilization_date);
"""
        _execute(sql)

        sql = f"""
create table if not exists {cls.SCHEMA_NAME}.{cls.PARTITIONED_TABLE_NAME} (
    id bigserial,
    ref_id int,
    utilization_code int not null,
    label text not null,
    data numeric(15,4),
    primary key (utilization_date, id)
)
partition by list (utilization_date);
"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        sql = f"""
drop table if exists {cls.SCHEMA_NAME}.{cls.PARTITIONED_TABLE_NAME} ;
"""
        _execute(sql)

    def execute(self, sql, params=None):
        return _execute(sql, params)

    def drop_all_partitions(self):
        PartitionedTable.objects.filter(
            schema_name=self.SCHEMA_NAME, partition_of_table_name=self.PARTITIONED_TABLE_NAME
        ).delete()

    def test_input_scrub(self):
        """Test input dict value scrubbing"""
        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "id": 1000,
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_default",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_parameters": {
                    "default": True,
                    "from": datetime.datetime(2021, 1, 1),
                    "to": datetime.date(2021, 2, 1),
                },
                "active": True,
            }
            dp, dc = ppart.get_or_create_partition(part_rec)
            self.assertTrue(bool(dp) and dc, f"bool(dp) = {bool(dp)}; dc = {dc}")
            self.assertFalse("id" in part_rec, '"id" still in part_rec')
            self.assertTrue(isinstance(part_rec["partition_parameters"]["from"], str))
            self.assertTrue(isinstance(part_rec["partition_parameters"]["to"], str))

            dp.delete()

    def test_call_with_default(self):
        """Test input dict value scrubbing"""
        with schema_context(self.SCHEMA_NAME):
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_default",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_parameters": {"default": True},
                "active": True,
            }
            default_partition, _ = PartitionedTable.objects.get_or_create(
                schema_name=self.SCHEMA_NAME,
                table_name=part_rec["table_name"],
                partition_parameters__default=True,
                defaults=part_rec,
            )
            dp, dc = ppart.get_or_create_partition(part_rec, _default_partition=default_partition)
            self.assertTrue(dp == default_partition, "get_or_create_partition did not return the default partition")
            self.assertFalse(dc, "get_or_create_partition with default says it created a default partition")

            dp.delete()

    def test_create_default_partition(self):
        """Test that a default partition can be explicitly created"""
        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_default",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_parameters": {"default": True},
                "active": True,
            }
            dp, dc = ppart.get_or_create_partition(part_rec)
            self.assertTrue(bool(dp) and dc, "Default partition not created")
            self.assertEqual(dp.table_name, part_rec["table_name"])
            self.assertTrue(dp.partition_parameters["default"])

            dp.delete()

    def test_create_partition_creates_default(self):
        """Test that creating a data partition will also create the default partition, if needed"""
        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_2021_01",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_type": "range",
                "partition_col": "utilization_date",
                "partition_parameters": {"default": False, "from": "2021-01-01", "to": "2021-02-01"},
                "active": True,
            }
            p, c = ppart.get_or_create_partition(part_rec)
            self.assertTrue(bool(p), f"Partition {part_rec['table_name']} creation failed")
            self.assertTrue(c, f"Partition {part_rec['table_name']} was not created")
            self.assertEqual(part_rec["table_name"], p.table_name)
            self.assertEqual(part_rec["partition_of_table_name"], p.partition_of_table_name)
            self.assertEqual(part_rec["partition_parameters"], p.partition_parameters)

            # This is using an "internal" function that the main interface will call
            dp, dc = ppart._get_or_create_default_partition(part_rec)
            self.assertTrue(bool(dp), "Failed to get tracking record for default partition")
            self.assertFalse(dc, "Default partition was created when it should not have been")

            dp.delete()
            p.delete()

    def test_get_existing_default_partition(self):
        """Test that an existing default partition can be retrieved without creation"""
        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_default",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_parameters": {"default": True},
                "active": True,
            }
            dp, dc = ppart.get_or_create_partition(part_rec)
            self.assertTrue(bool(dp) and dc, "Default partition not created for test")

            dp2, dc2 = ppart.get_or_create_partition(part_rec)
            self.assertFalse(dc2, "Default partition marked as created when it should exist")
            self.assertEqual(dp, dp2, "Different default partitions returned.")

            dp.delete()

    def test_get_existing_partition(self):
        """Test that an existing partition can be retrieved without creation"""
        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": self.PARTITIONED_TABLE_NAME + "_2021_01",
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_type": "range",
                "partition_col": "utilization_date",
                "partition_parameters": {"default": False, "from": "2021-01-01", "to": "2021-02-01"},
                "active": True,
            }
            p, c = ppart.get_or_create_partition(part_rec)
            self.assertTrue(bool(p) and c, "Partition not created for test")

            p2, c2 = ppart.get_or_create_partition(part_rec)
            self.assertFalse(c2, "Partition marked as created when it should exist")
            self.assertEqual(p, p2, "Different partitions returned.")

            p.delete()

    def test_overlapping_data_in_default(self):
        """Test that overlapping data in the default partition is moved to the desired partition"""
        DEFAULT_PART_NAME = f"{self.PARTITIONED_TABLE_NAME}_default"
        PART_01_NAME = f"{self.PARTITIONED_TABLE_NAME}_2021_01"
        PART_02_NAME = f"{self.PARTITIONED_TABLE_NAME}_2021_02"

        with schema_context(self.SCHEMA_NAME):
            self.drop_all_partitions()
            part_rec = {
                "schema_name": self.SCHEMA_NAME,
                "table_name": PART_01_NAME,
                "partition_of_table_name": self.PARTITIONED_TABLE_NAME,
                "partition_type": "range",
                "partition_col": "utilization_date",
                "partition_parameters": {"default": False, "from": "2021-01-01", "to": "2021-02-01"},
                "active": True,
            }
            p01, created = ppart.get_or_create_partition(part_rec)
            self.assertTrue(created, "Partition 1 was not created")

            sql = f"""
INSERT INTO {self.SCHEMA_NAME}.{self.PARTITIONED_TABLE_NAME} (utilization_date, label)
VALUES (%s, %s), (%s, %s), (%s, %s) ;
"""
            self.execute(sql, ("2021-01-01", "test 01", "2021-02-01", "test 02", "2021-03-01", "test 03"))

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{self.PARTITIONED_TABLE_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 3, "Initial load failed")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{PART_01_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 1, f"Partition 2021_01 had {ct} but 1 expected")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{DEFAULT_PART_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 2, f"Default partition had {ct} but 2 expected")

            part_rec["table_name"] = PART_02_NAME
            part_rec["partition_parameters"]["from"] = "2021-02-01"
            part_rec["partition_parameters"]["to"] = "2021-03-01"
            p02, created = ppart.get_or_create_partition(part_rec)
            self.assertTrue(created, "Partition 2 was not created")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{self.PARTITIONED_TABLE_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 3, f"Total record count changed {ct} (should be 3)")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{PART_01_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 1, f"Partition 2021_01 had {ct} but 1 expected")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{PART_02_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 1, f"Partition 2021_02 had {ct} but 1 expected")

            sql = f"""
select count(*) from {self.SCHEMA_NAME}.{DEFAULT_PART_NAME} ;
"""
            cur = self.execute(sql)
            ct = cur.fetchone()[0]
            self.assertEqual(ct, 1, f"Default partition had {ct} but 1 expected")

            p01.delete()
            p02.delete()
            ppart._get_or_create_default_partition(part_rec)[0].delete()


class TestPGPartition(IamTestCase):
    @classmethod
    def setUpClass(cls):
        _execute("SET log_min_messages = NOTICE;")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        _execute("SET log_min_messages = WARNING;")
        super().tearDownClass()

    def execute(self, sql, params=None):
        return _execute(sql, params)

    def _clean_test(self):
        sql = f"""
drop table if exists {self.schema_name}.__pg_partition_test cascade;
"""
        self.execute(sql)

        sql = f"""
drop table if exists {self.schema_name}.__pg_part_fk_test cascade;
"""
        self.execute(sql)

    def _setup_test(self, matview=False, indexes=False, foreign_key=False):
        sql = f"""
create table if not exists {self.schema_name}.__pg_part_fk_test (
    id serial primary key,
    data text not null
);
"""
        self.execute(sql)

        sql = f"""
create table if not exists {self.schema_name}.__pg_partition_test (
    id bigserial primary key,
    ref_id int,
    utilization_date date not null,
    label text not null,
    data numeric(15,4)
);
"""
        self.execute(sql)

        if foreign_key:
            sql = f"""
alter table {self.schema_name}.__pg_partition_test
      add constraint pg_part_fkey foreign key (ref_id) references {self.schema_name}.__pg_part_fk_test (id);
"""
            self.execute(sql)

        if indexes:
            sql = f"""
create index ix_pg_part_ref_id on {self.schema_name}.__pg_partition_test (ref_id);
"""
            self.execute(sql)

        if matview:
            sql = f"""
create materialized view {self.schema_name}.__data_by_ref_label as
select ref_id,
       label,
       sum(data)
  from {self.schema_name}.__pg_partition_test
 group
    by ref_id,
       label
  with data;
"""
            self.execute(sql)
            sql = f"""
create index ix_data_by_ref_label on {self.schema_name}.__data_by_ref_label (ref_id, label);
"""
            self.execute(sql)

    def _is_partitioned(self):
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
        return self.execute(sql, (self.schema_name, "__pg_partition_test")).fetchone()[0]

    def _get_test_tables(self):
        sql = """
select table_name
  from information_schema.tables
 where table_schema = %s
   and table_name ~ %s;
"""
        return {r[0] for r in self.execute(sql, (self.schema_name, "^__pg_"))}

    def _get_table_constraints(self):
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
   and t.relkind = any( '{r,p}'::text[] )
  join pg_namespace n
    on n.oid = t.relnamespace
  left
  join pg_class f
    on f.oid = c.confrelid
   and f.relkind = any( '{r,p}'::text[] )
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
        cur = self.execute(sql, (self.schema_name, "__pg_partition_test"))
        cols = [c.name for c in cur.description]
        res = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        return res

    def _get_indexes(self):
        sql = """
select *
  from pg_indexes
 where schemaname = %s
   and tablename = any( %s::text[] )
 order
    by tablename;
"""
        cur = self.execute(sql, (self.schema_name, ["__pg_partition_test", "__data_by_ref_label"]))
        cols = [c.name for c in cur.description]
        res = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        return res

    def _get_views(self):
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
   AND source_table.relname = %s
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
        cur = self.execute(sql, (self.schema_name, "__pg_partition_test"))
        cols = [c.name for c in cur.description]
        res = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        return res

    def _init_data(self):
        sql = f"""
insert into {self.schema_name}.__pg_part_fk_test (data) values ('eek') returning *;
"""
        cur = self.execute(sql)
        rec = dict(zip((d.name for d in cur.description), cur.fetchone()))
        sql = f"""
insert into {self.schema_name}.__pg_partition_test (ref_id, utilization_date, label, data)
values
(null, '2020-01-01'::date, 'no-ref', 95.25),
(%s, '2020-01-01'::date, 'has-ref', 105.25),
(%s, '2020-02-01'::date, 'eek-ref', 115.25) ;
"""
        self.execute(sql, [rec["id"], rec["id"]])

    def _count_data(self, table):
        sql = f"""
select count(*) from {self.schema_name}.{table} ;
"""
        cur = self.execute(sql)
        return cur.fetchone()[0]

    def test_default_repr(self):
        """
        Test repr(Default) == str(Default)
        """
        self.assertEqual(repr(ppart.Default(1)), str(ppart.Default(1)))
        self.assertEqual(repr(ppart.Default(None)), str(ppart.Default(None)))

    def test_no_sql_execute(self):
        """
        Test calling execute with no sql returns None
        """
        self.assertTrue(ppart.conn_execute(None) is None)

    def test_fetch_with_none(self):
        """
        Test calling fetch routines with none returns empty object
        """
        self.assertEqual(ppart.fetchall(None), [])
        self.assertEqual(ppart.fetchone(None), {})

    def test_resolve_schema(self):
        """
        Test resolving current_schema
        """
        schema = ppart.resolve_schema(ppart.CURRENT_SCHEMA)
        self.assertNotEqual(schema, ppart.CURRENT_SCHEMA)

    def test_resolve_schema_with_schema(self):
        """
        Test resolving specified schema
        """
        schema = ppart.resolve_schema("public")
        self.assertEqual(schema, "public")

    def test_partition_table_base(self):
        """
        Test partition of table structure only
        """
        self._clean_test()
        self._setup_test()

        self.assertFalse(self._is_partitioned())
        self.assertEqual(len(self._get_indexes()), 1)  # PK
        self.assertEqual(len(self._get_views()), 0)
        self.assertEqual(len(self._get_table_constraints()), 1)  # PK

        schema = self.schema_name
        source_table = "__pg_partition_test"
        target_table = "__p_pg_partition_test"
        pk_seq = ppart.SequenceDefinition(
            schema,
            "__p_pg_part_table_test_id_seq",
            copy_sequence={"schema_name": schema, "table_name": "__pg_partition_test", "column_name": "id"},
        )
        pk_coldef = ppart.ColumnDefinition(
            schema, target_table=target_table, column_name="id", default=ppart.Default(pk_seq)
        )
        pk_def = ppart.PKDefinition("__p_pg_partition_test_pkey", ["utilization_date", "id"])
        converter = ppart.ConvertToPartition(
            source_table,
            "utilization_date",
            target_table_name=target_table,
            pk_def=pk_def,
            col_def=[pk_coldef],
            target_schema=schema,
            source_schema=schema,
        )
        converter.convert_to_partition()
        tables = self._get_test_tables()

        self.assertTrue(self._is_partitioned())
        self.assertTrue(source_table + "_default" in tables)
        self.assertEqual(len([t for t in tables if t.startswith(source_table)]), 2)
        self.assertEqual(len(self._get_indexes()), 1)  # PK
        self.assertEqual(len(self._get_views()), 0)
        self.assertEqual(len(self._get_table_constraints()), 1)  # PK

        self._clean_test()

    def test_partition_table_full(self):
        """
        Test partitioning of table structure, dependent structures and data copy
        """
        self._clean_test()
        self._setup_test(matview=True, indexes=True, foreign_key=True)

        self._init_data()

        self.assertFalse(self._is_partitioned())
        self.assertEqual(len(self._get_indexes()), 3)  # PK + FK + matview
        self.assertEqual(len(self._get_views()), 1)
        self.assertEqual(len(self._get_table_constraints()), 2)  # PK + FK
        self.assertEqual(self._count_data("__pg_partition_test"), 3)

        schema = self.schema_name
        source_table = "__pg_partition_test"
        target_table = "__p_pg_partition_test"
        pk_seq = ppart.SequenceDefinition(
            schema,
            "__p_pg_parttition_test_id_seq",
            copy_sequence={"schema_name": schema, "table_name": "__pg_partition_test", "column_name": "id"},
        )
        pk_coldef = ppart.ColumnDefinition(
            schema, target_table=target_table, column_name="id", default=ppart.Default(pk_seq)
        )
        pk_def = ppart.PKDefinition("__p_pg_partition_test_pkey", ["utilization_date", "id"])
        converter = ppart.ConvertToPartition(
            source_table,
            "utilization_date",
            target_table_name=target_table,
            pk_def=pk_def,
            col_def=[pk_coldef],
            target_schema=schema,
            source_schema=schema,
        )
        converter.convert_to_partition()
        tables = self._get_test_tables()
        check_tables = {
            source_table + "_default",
            source_table + "_2020_01",
            source_table + "_2020_02",
            source_table,
            "__pg_part_fk_test",
        }

        self.assertTrue(self._is_partitioned())
        self.assertEqual(check_tables, tables)
        self.assertEqual(len([t for t in tables if t.startswith(source_table)]), 4)
        self.assertEqual(len(self._get_indexes()), 3)  # PK + FK + matview
        self.assertEqual(len(self._get_views()), 1)
        self.assertEqual(len(self._get_table_constraints()), 2)  # PK + FK
        self.assertEqual(self._count_data("__pg_partition_test"), 3)
        self.assertEqual(self._count_data("__pg_partition_test_2020_01"), 2)
        self.assertEqual(self._count_data("__pg_partition_test_2020_02"), 1)
        self.assertEqual(self._count_data("__pg_partition_test_default"), 0)

        self._clean_test()

    def test_convert_partitioned_table_exception(self):
        """
        Test that converting a table that is already partitioned raises TypeError
        """
        self._clean_test()
        self._setup_test()

        self.assertFalse(self._is_partitioned())
        schema = self.schema_name
        source_table = "__pg_partition_test"
        target_table = "__p_pg_partition_test"
        pk_seq = ppart.SequenceDefinition(
            schema,
            "__p_pg_part_table_test_id_seq",
            copy_sequence={"schema_name": schema, "table_name": "__pg_partition_test", "column_name": "id"},
        )
        pk_coldef = ppart.ColumnDefinition(
            schema, target_table=target_table, column_name="id", default=ppart.Default(pk_seq)
        )
        pk_def = ppart.PKDefinition("__p_pg_partition_test_pkey", ["utilization_date", "id"])
        converter = ppart.ConvertToPartition(
            source_table,
            "utilization_date",
            target_table_name=target_table,
            pk_def=pk_def,
            col_def=[pk_coldef],
            target_schema=schema,
            source_schema=schema,
        )
        converter.convert_to_partition()
        tables = self._get_test_tables()

        self.assertTrue(self._is_partitioned())
        self.assertTrue(source_table + "_default" in tables)

        with self.assertRaises(TypeError):
            # These get flip-flopped after the converter runs successfully
            # So flip 'em back
            converter.source_table_name = converter.partitioned_table_name
            converter.convert_to_partition()

        self._clean_test()

    def test_repartition_crawler_query_all(self):
        """
        Test that the schema crawler will return all schemata and all partitioned tables
        """
        res = ppart.get_partitioned_tables_with_default()
        schemata = set()
        tables = set()
        for rec in res:
            schemata.add(rec["schema_name"])
            tables.add(rec["partitioned_table"])

        self.assertTrue(len(schemata) > 1)
        self.assertTrue(len(tables) > 1)

    def test_repartition_crawler_query_one_schema(self):
        """
        Test that the schema crawler will return all schemata and all partitioned tables
        """
        res = ppart.get_partitioned_tables_with_default(schema_name=self.schema_name)
        schemata = set()
        tables = set()
        for rec in res:
            schemata.add(rec["schema_name"])
            tables.add(rec["partitioned_table"])

        self.assertEqual(len(schemata), 1)
        self.assertTrue(len(tables) > 1)

    def test_repartition_crawler_query_one_table(self):
        """
        Test that the schema crawler will return all schemata and all partitioned tables
        """
        res = ppart.get_partitioned_tables_with_default(
            partitioned_table_name="reporting_ocpusagelineitem_daily_summary"
        )
        schemata = set()
        tables = set()
        for rec in res:
            schemata.add(rec["schema_name"])
            tables.add(rec["partitioned_table"])

        self.assertEqual(len(tables), 1)
        self.assertTrue(len(schemata) > 1)

    def test_repartition_table(self):
        """
        Repartition one table using class interface
        """
        with schema_context(self.schema_name):
            aws_lids = AWSCostEntryLineItemDailySummary.objects.order_by("-usage_start")[0]
            aws_lids.usage_start = aws_lids.usage_start.replace(year=(aws_lids.usage_start.year + 10))
            aws_lids.save()
            with conn.cursor() as cur:
                cur.execute(
                    f"select count(*) as num_recs from {AWSCostEntryLineItemDailySummary._meta.db_table}_default;"
                )
                res = cur.fetchone()[0]
            self.assertEqual(res, 1)

            ppart.PartitionDefaultData(
                self.schema_name, AWSCostEntryLineItemDailySummary._meta.db_table
            ).repartition_default_data()

            with conn.cursor() as cur:
                cur.execute(
                    f"""
select count(*) as num_recs
  from {AWSCostEntryLineItemDailySummary._meta.db_table}_default;
"""
                )
                res = cur.fetchone()[0]
            self.assertEqual(res, 0)

            newpart = f"""{AWSCostEntryLineItemDailySummary._meta.db_table}_{aws_lids.usage_start.strftime("%Y_%m")}"""
            with conn.cursor() as cur:
                cur.execute(
                    f"""
select count(*) as num_recs
  from {newpart};
"""
                )
                res = cur.fetchone()[0]
            self.assertEqual(res, 1)

    def test_repartition_all_tables(self):
        """
        Repartition using driver function
        """
        with schema_context(self.schema_name):
            aws_lids = AWSCostEntryLineItemDailySummary.objects.order_by("-usage_start")[0]
            aws_lids.usage_start = aws_lids.usage_start.replace(year=(aws_lids.usage_start.year + 11))
            aws_lids.save()
            ocp_lids = OCPUsageLineItemDailySummary.objects.order_by("-usage_start")[0]
            ocp_lids.usage_start = ocp_lids.usage_start.replace(year=(aws_lids.usage_start.year + 11))
            ocp_lids.save()
            with conn.cursor() as cur:
                cur.execute(
                    f"""
select (
    select count(*) as a_num_recs
      from {AWSCostEntryLineItemDailySummary._meta.db_table}_default
) as "num_aws_lids_default",
(
    select count(*) as o_num_recs
      from {OCPUsageLineItemDailySummary._meta.db_table}_default
) as "num_ocp_lids_default";
"""
                )
                res = cur.fetchone()
            self.assertTrue(res[0] > 0)
            self.assertTrue(res[1] > 0)

            ppart.repartition_default_data(schema_name=self.schema_name)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
select (
    select count(*) as a_num_recs
      from {AWSCostEntryLineItemDailySummary._meta.db_table}_default
) as "num_aws_lids_default",
(
    select count(*) as o_num_recs
      from {OCPUsageLineItemDailySummary._meta.db_table}_default
) as "num_ocp_lids_default";
"""
                )
                res = cur.fetchone()
            self.assertEqual(res, (0, 0))

            a_newpart = f"{AWSCostEntryLineItemDailySummary._meta.db_table}_{aws_lids.usage_start.strftime('%Y_%m')}"
            o_newpart = f"{OCPUsageLineItemDailySummary._meta.db_table}_{ocp_lids.usage_start.strftime('%Y_%m')}"
            with conn.cursor() as cur:
                cur.execute(
                    f"""
select (
    select count(*) as a_num_recs
      from {a_newpart}
) as "num_aws_lids_default",
(
    select count(*) as o_num_recs
      from {o_newpart}
) as "num_ocp_lids_default";
"""
                )
                res = cur.fetchone()
            self.assertEqual(res, (1, 1))

            # test that insert with new partition bounds will work successfully
            new_ocp_lids = OCPUsageLineItemDailySummary(uuid=uuid.uuid4())
            for col in (x for x in new_ocp_lids._meta.fields if x.name != "uuid"):
                setattr(new_ocp_lids, col.name, getattr(ocp_lids, col.name, None))
            new_day = (
                new_ocp_lids.usage_start.day + 1
                if new_ocp_lids.usage_start.day < 28
                else new_ocp_lids.usage_start.day - 1
            )
            new_ocp_lids.usage_start = ocp_lids.usage_start.replace(day=new_day)
            new_ocp_lids.save()

            with conn.cursor() as cur:
                cur.execute(
                    f"""
select (
    select count(*) as a_num_recs
      from {a_newpart}
) as "num_aws_lids_default",
(
    select count(*) as o_num_recs
      from {o_newpart}
) as "num_ocp_lids_default";
"""
                )
                res = cur.fetchone()
            self.assertEqual(res, (1, 2))

    def test_subpartition(self):
        """Test multiple levels of partitioning"""
        partitioned_table_name = "_eek_partitioned"
        new_partitioned_table_sql = f"""
create table {self.schema_name}.{partitioned_table_name} (
    id bigserial,
    usage_start date not null,
    provider_id text not null,
    data jsonb
)
partition by range (usage_start);
"""
        _execute(new_partitioned_table_sql)
        with schema_context(self.schema_name):
            # partition first by usage_start (this is the default partition)
            usage_default_partition = PartitionedTable(
                schema_name=self.schema_name,
                table_name=f"{partitioned_table_name}_default",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": True},
                active=True,
            )
            usage_default_partition.save()
            res = _get_table_partition_info(self.schema_name, usage_default_partition.table_name)
            self.assertEqual({"relkind": "r", "relispartition": True}, res)

            # partition first by usage_start, then by provider_id (this is the sub-partition)
            usage_partition = PartitionedTable(
                schema_name=self.schema_name,
                table_name=f"{partitioned_table_name}_2020_01",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": False, "from": "2020-01-01", "to": "2020-02-01"},
                subpartition_type=PartitionedTable.LIST,
                subpartition_col="provider_id",
                active=True,
            )
            usage_partition.save()
            res = _get_table_partition_info(self.schema_name, usage_partition.table_name)
            self.assertEqual({"relkind": "p", "relispartition": True}, res)

            # Create a default for the sub-partitioned data. This is a leaf partition
            usage_list_default_partition = PartitionedTable(
                schema_name=self.schema_name,
                table_name=f"{usage_partition.table_name}_default",
                partition_of_table_name=usage_partition.table_name,
                partition_type=PartitionedTable.LIST,
                partition_col="provider_id",
                partition_parameters={"default": True},
                active=True,
            )
            usage_list_default_partition.save()
            res = _get_table_partition_info(self.schema_name, usage_list_default_partition.table_name)
            self.assertEqual({"relkind": "r", "relispartition": True}, res)

            # This is a leaf partition that will hold our "good" data
            usage_list_partition = PartitionedTable(
                schema_name=self.schema_name,
                table_name=f"{usage_partition.table_name}_a_d",
                partition_of_table_name=usage_partition.table_name,
                partition_type=PartitionedTable.LIST,
                partition_col="provider_id",
                partition_parameters={"default": False, "in": "ABC,DEF"},
                active=True,
            )
            usage_list_partition.save()
            res = _get_table_partition_info(self.schema_name, usage_list_partition.table_name)
            self.assertEqual({"relkind": "r", "relispartition": True}, res)

            # Add some data to various partitions
            insert_sql = f"""
insert into {self.schema_name}.{partitioned_table_name} (usage_start, provider_id, data)
values
('2020-01-15'::date, 'ABC', '{{"stuffs": 1}}'::jsonb),
('2020-01-15'::date, 'DEF', '{{"stuffs": 2}}'::jsonb),
('2020-01-15'::date, 'GHI', '{{"stuffs": 3}}'::jsonb),
('2020-02-15'::date, 'ABC', '{{"stuffs": "FOUR"}}'::jsonb);
"""
            _execute(insert_sql)
            expected_good_sql = f"""
select count(*) from {self.schema_name}.{usage_list_partition.table_name} ;
"""
            expected_good_count = _execute(expected_good_sql).fetchone()[0]

            expected_usage_list_default_sql = f"""
select count(*) from {self.schema_name}.{usage_list_default_partition.table_name} ;
"""
            expected_usage_list_default_count = _execute(expected_usage_list_default_sql).fetchone()[0]

            expected_usage_default_sql = f"""
select count(*) from {self.schema_name}.{usage_default_partition.table_name} ;
"""
            expected_usage_default_count = _execute(expected_usage_default_sql).fetchone()[0]

            # Verify that the records went to the correct partitions
            self.assertEqual(expected_good_count, 2)
            self.assertEqual(expected_usage_list_default_count, 1)
            self.assertEqual(expected_usage_default_count, 1)

            # Cleanup
            usage_list_partition.delete()
            usage_list_default_partition.delete()
            usage_partition.delete()
            usage_default_partition.delete()
            _execute(f"""drop table {self.schema_name}.{partitioned_table_name} ;""")

            # Verify that triggers cleaned up the tables
            self.assertIsNone(_get_table_partition_info(self.schema_name, usage_list_partition.table_name))
            self.assertIsNone(_get_table_partition_info(self.schema_name, usage_list_default_partition.table_name))
            self.assertIsNone(_get_table_partition_info(self.schema_name, usage_partition.table_name))
            self.assertIsNone(_get_table_partition_info(self.schema_name, usage_default_partition.table_name))
            self.assertIsNone(_get_table_partition_info(self.schema_name, partitioned_table_name))
