from django.db import connection as conn

from . import pg_partition as ppart
from api.iam.test.iam_test_case import IamTestCase


class TestPGPartition(IamTestCase):
    def execute(self, sql, params=None):
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur

    def _clean_test(self):
        sql = """
drop table if exists public.__pg_partition_test cascade;
"""
        self.execute(sql)

        sql = """
drop table if exists public.__pg_part_fk_test cascade;
"""
        self.execute(sql)

        sql = """
drop table if exists public.partitioned_tables cascade;
"""
        self.execute(sql)

    def _setup_test(self, matview=False, indexes=False, foreign_key=False):
        sql = """
create table if not exists public.partitioned_tables
(
    schema_name text not null default 'public',
    table_name text not null,
    partition_of_table_name text not null,
    partition_type text not null,
    partition_col text not null,
    partition_parameters jsonb not null,
    constraint table_partition_pkey primary key (schema_name, table_name)
);
"""
        self.execute(sql)

        sql = """
create table public.__pg_part_fk_test (
    id serial primary key,
    data text not null
);
"""
        self.execute(sql)

        sql = """
create table public.__pg_partition_test (
    id bigserial primary key,
    ref_id int,
    utilization_date date not null,
    label text not null,
    data numeric(15,4)
);
"""
        self.execute(sql)

        if foreign_key:
            sql = """
alter table public.__pg_partition_test
      add constraint pg_part_fkey foreign key (ref_id) references public.__pg_part_fk_test (id);
"""
            self.execute(sql)

        if indexes:
            sql = """
create index ix_pg_part_ref_id on public.__pg_partition_test (ref_id);
"""
            self.execute(sql)

        if matview:
            sql = """
create materialized view __data_by_ref_label as
select ref_id,
       label,
       sum(data)
  from public.__pg_partition_test
 group
    by ref_id,
       label
  with data;
"""
            self.execute(sql)
            sql = """
create index ix_data_by_ref_label on __data_by_ref_label (ref_id, label);
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
                                     where relnamespace = 'public'::regnamespace
                                       and relname = '__pg_partition_test'
                                  )
              )::boolean as "is_partitioned";
"""
        return self.execute(sql).fetchone()[0]

    def _get_test_tables(self):
        sql = """
select table_name
  from information_schema.tables
 where table_schema = 'public'
   and table_name ~ '^__pg_';
"""
        return {r[0] for r in self.execute(sql)}

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
   and n.nspname = 'public'
   and t.relname = '__pg_partition_test'
 order
    by t.relname,
       case when c.contype = 'p'
                 then 0
            else 1
       end::int
"""
        cur = self.execute(sql)
        cols = [c.name for c in cur.description]
        res = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        return res

    def _get_indexes(self):
        sql = """
select *
  from pg_indexes
 where schemaname = 'public'
   and tablename = any( '{__pg_partition_test,__data_by_ref_label}'::text[] )
 order
    by tablename;
"""
        cur = self.execute(sql)
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
   AND source_table.relnamespace = 'public'::regnamespace
   AND source_table.relname = '__pg_partition_test'
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
        cur = self.execute(sql)
        cols = [c.name for c in cur.description]
        res = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        return res

    def test_resolve_schema(self):
        schema = ppart.resolve_schema(ppart.CURRENT_SCHEMA)
        self.assertNotEqual(schema, ppart.CURRENT_SCHEMA)

    def test_partition_table_base(self):
        self._clean_test()
        self._setup_test()

        self.assertFalse(self._is_partitioned())
        self.assertEqual(len(self._get_indexes()), 1)  # PK
        self.assertEqual(len(self._get_views()), 0)
        self.assertEqual(len(self._get_table_constraints()), 1)  # PK

        schema = "public"
        source_table = "__pg_partition_test"
        target_table = "__p_pg_partition_test"
        pk_seq = ppart.SequenceDefinition(
            schema,
            "__p_pg_part_table_test_id_seq",
            copy_sequence={"schema_name": "public", "table_name": "__pg_partition_test", "column_name": "id"},
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
        self._clean_test()
        self._setup_test(matview=True, indexes=True, foreign_key=True)

        sql = """
insert into public.__pg_part_fk_test (data) values ('eek') returning *;
"""
        cur = self.execute(sql)
        rec = dict(zip((d.name for d in cur.description), cur.fetchone()))
        sql = """
insert into public.__pg_partition_test (ref_id, utilization_date, label, data)
values
(null, '2020-01-01'::date, 'no-ref', 95.25),
(%s, '2020-01-01'::date, 'has-ref', 105.25),
(%s, '2020-02-01'::date, 'eek-ref', 115.25) ;
"""
        self.execute(sql, [rec["id"], rec["id"]])

        self.assertFalse(self._is_partitioned())
        self.assertEqual(len(self._get_indexes()), 3)  # PK + FK + matview
        self.assertEqual(len(self._get_views()), 1)
        self.assertEqual(len(self._get_table_constraints()), 2)  # PK + FK

        schema = "public"
        source_table = "__pg_partition_test"
        target_table = "__p_pg_partition_test"
        pk_seq = ppart.SequenceDefinition(
            schema,
            "__p_pg_parttition_test_id_seq",
            copy_sequence={"schema_name": "public", "table_name": "__pg_partition_test", "column_name": "id"},
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

        self._clean_test()
