/*
Copyright 2020 Red Hat, Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

DROP FUNCTION IF EXISTS public.clone_schema(text, text, boolean, boolean);
CREATE OR REPLACE FUNCTION public.clone_schema(
    source_schema text,
    dest_schema text,
    copy_data boolean DEFAULT false,
    _verbose boolean DEFAULT false
) RETURNS boolean AS $$
DECLARE
    object_rec record;
    object2_rec record;
    src_schema text;
    dst_schema text;
    source_obj text;
    dest_obj text;
    ix_stmt text;
    seqval bigint;
    tenant_ident text[];
BEGIN
    dst_schema = quote_ident(dest_schema);
    src_schema = quote_ident(source_schema);

    /* Check if source schema exists */
    PERFORM oid
       FROM pg_namespace
      WHERE nspname = source_schema;
    IF NOT FOUND
    THEN
        RAISE WARNING 'Source schema % does not exist.', src_schema;
        RETURN false;
    END IF;

    /* Check if dest schema exists */
    PERFORM oid
       FROM pg_namespace
      WHERE nspname = dest_schema;
    IF FOUND
    THEN
        RAISE INFO 'Destination schema % already exists.', dst_schema;
        RETURN false;
    END IF;

    SET LOCAL search_path = public;

    /*
     * Create the new schema
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating schema %', dst_schema;
    END IF;

    EXECUTE 'CREATE SCHEMA ' || dst_schema || ' ;';

    /*
     * Create sequences
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating sequences for %', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT c.relname as "sequence_name",
               s.seqtypid::regtype::text as "sequence_type",
               s.seqstart as "sequence_start",
               s.seqincrement as "sequence_inc",
               s.seqmax as "sequence_max",
               s.seqmin as "sequence_min",
               s.seqcache as "sequence_cache",
               CASE WHEN s.seqcycle THEN ' CYCLE' ELSE ' NO CYCLE' END::text as "sequence_cycle"
          FROM pg_sequence s
          JOIN pg_class c
            ON c.oid = s.seqrelid
         WHERE c.relnamespace = source_schema::regnamespace
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    %.%', dst_schema, quote_ident(object_rec.sequence_name);
        END IF;
        EXECUTE 'CREATE SEQUENCE IF NOT EXISTS ' ||
                dst_schema || '.' || quote_ident(object_rec.sequence_name) ||
                ' AS ' || object_rec.sequence_type ||
                ' START WITH ' || object_rec.sequence_start ||
                ' INCREMENT BY ' || object_rec.sequence_inc ||
                ' MINVALUE ' || object_rec.sequence_min ||
                ' MAXVALUE ' || object_rec.sequence_max ||
                ' CACHE ' || object_rec.sequence_cache ||
                object_rec.sequence_cycle || ' ;';

        IF copy_data OR
           (object_rec.sequence_name ~ 'partitioned_tables') OR
           (object_rec.sequence_name ~ 'django_migrations')
        THEN
            EXECUTE 'SELECT setval(''' || dst_schema || '.' || quote_ident(object_rec.sequence_name) || '''::regclass, ' ||
                     '(SELECT last_value + 1 FROM ' ||
                     src_schema || '.' || quote_ident(object_rec.sequence_name) || ') );';
        END IF;
    END LOOP;

    /*
     * Create tables
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating tables for %', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT t.oid as "obj_id",
               t.relname::text as "table_name",
               t.relkind::text as "table_kind",
               CASE pt2.partstrat
                    WHEN 'h' THEN 'HASH'
                    WHEN 'l' THEN 'LIST'
                    WHEN 'r' THEN 'RANGE'
                    ELSE NULL
               END::text as "partition_type",
               pk.attname::text as "partition_key",
               t.relispartition as "is_partition",
               p.relname as "partitioned_table",
               pg_get_expr(t.relpartbound, t.oid) as "partition_expr"
          FROM pg_class t
          LEFT
          JOIN pg_inherits h
            ON h.inhrelid = t.oid
          LEFT
          JOIN pg_partitioned_table pt
            ON pt.partrelid = h.inhparent
          LEFT
          JOIN pg_class p
            ON p.oid = pt.partrelid
          LEFT
          JOIN pg_partitioned_table pt2
            ON pt2.partrelid = t.oid
          LEFT
          JOIN pg_attribute pk
            ON pk.attrelid = t.oid
           AND pk.attnum = pt2.partattrs::text::int2
         WHERE t.relnamespace = source_schema::regnamespace
           AND t.relkind in ('r', 'p')
         ORDER
            BY CASE WHEN t.relkind = 'p' THEN 0
                    ELSE 1
               END::int,
               t.relispartition
    LOOP
        dest_obj = dst_schema || '.' || quote_ident(object_rec.table_name);
        source_obj = src_schema || '.' || quote_ident(object_rec.table_name);

        IF object_rec.table_kind = 'p'
        THEN
            IF _verbose
            THEN
                RAISE INFO '    % (partitioned table)', dest_obj;
            END IF;
            EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' (LIKE ' || source_obj || ' INCLUDING ALL) ' ||
                    'PARTITION BY ' || object_rec.partition_type ||
                    ' ( ' || quote_ident(object_rec.partition_key) || ' ) ;';
        ELSIF object_rec.is_partition
        THEN
            IF _verbose
            THEN
                RAISE INFO '    % (table partition)', dest_obj;
            END IF;
            EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' PARTITION OF ' ||
                    dst_schema || '.' || quote_ident(object_rec.partitioned_table) || ' ' ||
                    object_rec.partition_expr || ' ;';
        ELSE
            IF _verbose
            THEN
                RAISE INFO '    % (table)', dest_obj;
            END IF;
            EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' (LIKE ' || source_obj || ' INCLUDING ALL) ;';
        END IF;

        IF (copy_data OR
            (object_rec.table_name ~ 'partitioned_tables') OR
            (object_rec.table_name ~ 'django_migrations')) AND
           (object_rec.table_kind = 'r')
        THEN
            IF _verbose
            THEN
                RAISE INFO '        Copying data...';
            END IF;
            EXECUTE 'INSERT INTO ' || dest_obj || ' SELECT * FROM ' || source_obj || ' ;';
        END IF;

        IF object_rec.table_name = 'partitioned_tables'
        THEN
            IF _verbose
            THEN
                RAISE INFO '        Update partitioned_tables schema data';
            END IF;
            EXECUTE 'UPDATE ' || dest_obj || ' SET schema_name = ' || quote_literal(dest_schema) || ' ;';
        END IF;

        IF NOT object_rec.is_partition
        THEN
            FOR object2_rec IN
                SELECT s.relname as "sequence_name",
                       d.refobjid::regclass::text as "owner_object",
                       a.attname::text as "owner_column"
                  FROM pg_depend d
                  JOIN pg_attribute a
                    ON a.attrelid = d.refobjid
                   AND a.attnum = d.refobjsubid
                  JOIN pg_class s
                    ON s.oid = d.objid
                   AND s.relkind = 'S'
                 WHERE d.refobjid = source_obj::regclass
            LOOP
                IF _verbose
                THEN
                    RAISE INFO '        Update primary key default';
                END IF;
                EXECUTE 'ALTER TABLE ' || dest_obj || ' ALTER COLUMN ' || quote_ident(object2_rec.owner_column) ||
                        ' SET DEFAULT nextval(''' || dst_schema || '.' || quote_ident(object2_rec.sequence_name) || '''::regclass);';

                IF _verbose
                THEN
                    RAISE INFO '        Update sequence owned-by table column';
                END IF;
                EXECUTE 'ALTER SEQUENCE ' || dst_schema || '.' || quote_ident(object2_rec.sequence_name) ||
                        ' OWNED BY ' || dest_obj || '.' || quote_ident(object2_rec.owner_column) || ' ;';
            END LOOP;
        END IF;
    END LOOP;

    /*
     * Create Foreign Key Constraints
     */
    IF _verbose
    THEN
        RAISE INFO 'Create foriegn key constraints for tables in "%"', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT rn.relname as "table_name",
               ct.conname as "constraint_name",
               'ALTER TABLE ' || dst_schema || '.' || quote_ident(rn.relname) ||
                            ' ADD CONSTRAINT ' || quote_ident(ct.conname) || ' ' ||
                            replace(pg_get_constraintdef(ct.oid), source_schema || '.', dst_schema || '.') ||
                            ' ;' as "alter_stmt"
          FROM pg_constraint ct
          JOIN pg_class rn
            ON rn.oid = ct.conrelid
         WHERE connamespace = source_schema::regnamespace
           AND rn.relkind in ('r', 'p')
           AND NOT rn.relispartition
           AND ct.contype = 'f'
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    %.%', object_rec.table_name, object_rec.constraint_name;
        END IF;
        EXECUTE object_rec.alter_stmt;
    END LOOP;

    /*
     * Create Views
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating views for %', dst_schema;
    END IF;
    FOR object_rec IN
        WITH RECURSIVE view_deps as (
        SELECT DISTINCT
               0 as depth,
               v.oid as view_oid,
               v.relname::text as view_name,
               v.relkind as view_kind,
               v.oid as dep_obj_id,
               v.relname::text as dep_obj_name,
               v.relkind as deb_obj_kind
          FROM pg_class v
         WHERE v.relnamespace = source_schema::regnamespace
           AND v.relkind IN ('v', 'm')
           AND NOT EXISTS (
                            SELECT 1 as x
                              FROM pg_depend d
                              JOIN pg_class c
                                ON c.oid = d.objid
                               AND c.relkind in ('m', 'v')
                             WHERE d.refobjid = v.oid
                          )
         UNION
        SELECT DISTINCT
               rv.depth + 1 as "depth",
               dv.oid as view_oid,
               dv.relname as view_name,
               dv.relkind as view_kind,
               rv.view_oid as ref_view_oid,
               rv.view_name as ref_view_name,
               rv.view_kind as ref_view_kind
          FROM pg_class dv
          JOIN pg_depend pd
            ON pd.objid = dv.oid
          JOIN view_deps as rv
            ON rv.view_oid = pd.refobjid
         WHERE dv.relnamespace = source_schema::regnamespace
           AND dv.relkind in ('m', 'v')
        ),
        base_view_def as (
        SELECT *,
               replace(pg_get_viewdef(view_oid), source_schema || '.', dst_schema || '.') as "view_def"
          FROM view_deps
        )
        SELECT bvd.view_name,
               CASE WHEN bvd.view_kind = 'm'
                         THEN 'MATERIALIZED VIEW'
                    ELSE 'VIEW'
               END::text as view_kind,
               CASE WHEN bvd.view_kind = 'm'
                         THEN substr(bvd.view_def, 1, length(bvd.view_def) - 1) || ' WITH DATA;'
                    ELSE bvd.view_def
               END::text as "view_def",
               COALESCE((SELECT array_agg(replace(pg_get_indexdef(i.indexrelid),
                                                                  source_schema || '.',
                                                                  dst_schema || '.'))::text[]
                           FROM pg_index i
                          WHERE i.indrelid = bvd.view_oid),
                        '{}'::text[]) as "view_indexes"
          FROM base_view_def bvd
         ORDER
            BY bvd.depth
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    %: "%"', object_rec.view_kind, object_rec.view_name;
        END IF;
        EXECUTE 'CREATE ' || object_rec.view_kind || ' ' ||
                dst_schema || '.' || quote_ident(object_rec.view_name) || ' AS ' ||
                object_rec.view_def;

        IF cardinality(object_rec.view_indexes) > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO '        Create indexes';
            END IF;
            FOREACH ix_stmt IN ARRAY object_rec.view_indexes
            LOOP
                EXECUTE ix_stmt;
            END LOOP;
        END IF;
    END LOOP;

    /*
     * Create functions
     */
    IF _verbose
    THEN
        RAISE INFO 'Create functions, procedures for "%"', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT proname as "func_name",
               CASE prokind
                    WHEN 'p' THEN 'PROCEDURE'
                    WHEN 'f' THEN 'FUNCTION'
                    WHEN 'a' THEN 'AGGREGATE'
                    WHEN 'w' THEN 'WINDOW'
                    ELSE 'UNKNOWN'
               END::text as "func_type",
               replace(pg_get_functiondef(oid), source_schema || '.', dst_schema || '.') as "func_stmt"
          FROM pg_proc
         WHERE pronamespace = source_schema::regnamespace
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    "%" "%"', object_rec.func_type, object_rec.func_name;
        END IF;
        EXECUTE object_rec.func_stmt;
    END LOOP;

    /*
     * Create triggers
     */
    IF _verbose
    THEN
        RAISE INFO 'Create triggers on objects in "%"', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT t.oid as "trigger_id",
               t.tgname::text as "trigger_name",
               c.relname::text as "table_name",
               replace(pg_get_triggerdef(t.oid), source_schema || '.', dst_schema || '.') as "trigger_def"
          FROM pg_trigger t
          JOIN pg_class c
            ON c.oid = t.tgrelid
           AND NOT c.relispartition
         WHERE c.relnamespace = source_schema::regnamespace
           AND t.tgconstraint = 0
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    "%"."%"', object_rec.table_name, object_rec.trigger_name;
        END IF;
        EXECUTE object_rec.trigger_def;
    END LOOP;

    /*
     *  Create rules
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating rules on objects in %', dst_schema;
    END IF;
    FOR object_rec IN
        SELECT tablename,
               rulename,
               replace(definition, source_schema || '.', dst_schema || '.') as "rule_def"
          FROM pg_rules
         WHERE schemaname = source_schema
    LOOP
        IF _verbose
        THEN
            RAISE INFO '    RULE "%" on "%"', object_rec.rulename, object_rec.tablename;
        END IF;
        EXECUTE object_rec.rule_def;
    END LOOP;

    /*
     * Create comments
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating comments on objects in %', dst_schema;
    END IF;
    FOR object_rec IN
        select t.oid,
               coalesce(c.attnum, -1) as "attnum",
               t.relkind,
               t.relname as "table_name",
               case when c.attname is not null then '."' || c.attname || '"' else '' end::text as "column_name",
               case when c.attname is null
                         then case t.relkind
                                   when 'm' then 'MATERIALIZED VIEW'
                                   when 'v' then 'VIEW'
                                   else 'TABLE'
                              end::text
                         else 'COLUMN' end::text as "comment_type",
               d.description
          from pg_description d
          join pg_class t
            on t.oid = d.objoid
          left
          join pg_attribute c
            on c.attrelid = t.oid
           and c.attnum = d.objsubid
         where t.relnamespace = source_schema::regnamespace
           and t.relkind = any('{r,p,v,m}'::text[])
         order
            by t.oid, "attnum"
    LOOP
        IF _verbose AND (object_rec.attnum = -1)
        THEN
            RAISE INFO '    % %', object_rec.comment_type, object_rec.table_name || object_rec.column_name;
        END IF;
        EXECUTE 'COMMENT ON ' || object_rec.comment_type || ' ' ||
                         dst_schema || '.' || quote_ident(object_rec.table_name) || object_rec.column_name || ' ' ||
                         'IS ' || quote_literal(object_rec.description) || ' ;';
    END LOOP;

    RETURN true;
END;
$$ LANGUAGE plpgsql;
