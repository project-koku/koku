--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

DROP FUNCTION IF EXISTS public.clone_schema(text, text, boolean, boolean);
CREATE OR REPLACE FUNCTION public.clone_schema(
    source_schema text,
    dest_schema text,
    copy_data boolean DEFAULT false,
    _verbose boolean DEFAULT false
) RETURNS boolean AS $$
DECLARE
    sequence_owner_info jsonb[];
    table_objects jsonb[];
    fk_objects jsonb[];
    view_objects jsonb[];
    function_objects jsonb[];
    trigger_objects jsonb[];
    rule_objects jsonb[];
    comment_objects jsonb[];
    jobject jsonb;
    src_schema text;
    dst_schema text;
    source_obj text;
    dest_obj text;
    ix_stmt text;
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
     * Gather data for copy
     */

    /* Sequence owner info */
    IF _verbose THEN
        RAISE INFO 'Gathering sequence owner data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'sequence_name', s.relname::text,
                   'owner_object', o.relname::text,
                   'owner_column', a.attname::text
               )
           ), '{}'::jsonb[])
      INTO sequence_owner_info
      FROM pg_class s
      JOIN pg_sequence ps
        ON ps.seqrelid = s.oid
      JOIN pg_depend d
        ON d.objid = s.oid
      JOIN pg_attribute a
        ON a.attrelid = d.refobjid
       AND a.attnum = d.refobjsubid
      JOIN pg_class o
        ON o.oid = d.refobjid
     WHERE s.relkind = 'S'
       AND o.relnamespace = source_schema::regnamespace
       AND NOT o.relispartition;

    IF _verbose THEN
        RAISE INFO '    Got %s schema owner objects...', cardinality(sequence_owner_info);
    END IF;

    /* Table objects */
    IF _verbose THEN
        RAISE INFO 'Gathering table object data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'obj_id', t.oid,
                   'table_name', t.relname::text,
                   'table_kind', t.relkind::text,
                   'partition_type', CASE pt2.partstrat
                                          WHEN 'h' THEN 'HASH'
                                          WHEN 'l' THEN 'LIST'
                                          WHEN 'r' THEN 'RANGE'
                                          ELSE NULL
                                     END::text,
                   'partition_key', pk.attname::text,
                   'is_partition', t.relispartition,
                   'partitioned_table', p.relname,
                   'partition_expr', pg_get_expr(t.relpartbound, t.oid)
              )
              ORDER BY t.relkind, t.relispartition
           ), '{}'::jsonb[])
      INTO table_objects
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
       AND t.relkind in ('r', 'p');

    IF _verbose THEN
        RAISE INFO '    Got %s table objects...', cardinality(table_objects);
    END IF;

    /* Foreign Key objects */
    IF _verbose THEN
        RAISE INFO 'Gathering foreign key constraint data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'table_name', rn.relname,
                   'constraint_name', ct.conname,
                   'alter_stmt', 'ALTER TABLE ' || dst_schema || '.' || quote_ident(rn.relname) ||
                                     ' ADD CONSTRAINT ' || quote_ident(ct.conname) || ' ' ||
                                     replace(pg_get_constraintdef(ct.oid), source_schema || '.', dst_schema || '.') ||
                                     ' ;'
               )
           ), '{}'::jsonb[])
    INTO fk_objects
    FROM pg_constraint ct
    JOIN pg_class rn
        ON rn.oid = ct.conrelid
    WHERE connamespace = source_schema::regnamespace
    AND rn.relkind in ('r', 'p')
    AND NOT rn.relispartition
    AND ct.contype = 'f';

    IF _verbose THEN
        RAISE INFO '    Got %s foreign key objects...', cardinality(fk_objects);
    END IF;

    /* View objects */
    IF _verbose THEN
        RAISE INFO 'Gathering view object data from %...', source_schema;
    END IF;

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
    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'view_name', bvd.view_name,
                   'depth', bvd.depth,
                   'view_kind', CASE WHEN bvd.view_kind = 'm'
                                          THEN 'MATERIALIZED VIEW'
                                     ELSE 'VIEW'
                                END::text,
                   'view_def', CASE WHEN bvd.view_kind = 'm'
                                         THEN substr(bvd.view_def, 1, length(bvd.view_def) - 1) || ' WITH DATA;'
                                    ELSE bvd.view_def
                               END::text,
                   'view_indexes', COALESCE((SELECT to_jsonb(array_to_json(array_agg(replace(pg_get_indexdef(i.indexrelid),
                                                                                     source_schema || '.',
                                                                                     dst_schema || '.'))))
                                               FROM pg_index i
                                              WHERE i.indrelid = bvd.view_oid),
                                            jsonb_build_array())
               )
               order by bvd.depth
           ), '{}'::jsonb[])
      INTO view_objects
      FROM base_view_def bvd;

    IF _verbose THEN
        RAISE INFO '    Got %s view objects...', cardinality(view_objects);
    END IF;

    /* Function objects */
    IF _verbose THEN
        RAISE INFO 'Gathering function/procedure object data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'func_name', proname,
                   'func_type', CASE prokind
                                     WHEN 'p' THEN 'PROCEDURE'
                                     WHEN 'f' THEN 'FUNCTION'
                                     WHEN 'a' THEN 'AGGREGATE'
                                     WHEN 'w' THEN 'WINDOW'
                                     ELSE 'UNKNOWN'
                                END::text,
                   'func_stmt', replace(pg_get_functiondef(oid), source_schema || '.', dst_schema || '.')
               )
           ), '{}'::jsonb[])
    INTO function_objects
    FROM pg_proc
    WHERE pronamespace = source_schema::regnamespace;

    IF _verbose THEN
        RAISE INFO '    Got %s function/procedure objects...', cardinality(function_objects);
    END IF;

    /* Trigger objects */
    IF _verbose THEN
        RAISE INFO 'Gathering trigger object data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'trigger_id', t.oid,
                   'trigger_name', t.tgname::text,
                   'table_name', c.relname::text,
                   'trigger_def', replace(pg_get_triggerdef(t.oid), source_schema || '.', dst_schema || '.')
               )
           ), '{}'::jsonb[])
      INTO trigger_objects
      FROM pg_trigger t
      JOIN pg_class c
        ON c.oid = t.tgrelid
       AND NOT c.relispartition
     WHERE c.relnamespace = source_schema::regnamespace
       AND t.tgconstraint = 0;

    IF _verbose THEN
        RAISE INFO '    Got %s trigger objects...', cardinality(trigger_objects);
    END IF;

    /* Rule objects */
    IF _verbose THEN
        RAISE INFO 'Gathering rule object data from %...', source_schema;
    END IF;

    SELECT coalesce(array_agg(
               jsonb_build_object(
                   'tablename', tablename,
                   'rulename', rulename,
                   'rule_def', replace(definition, source_schema || '.', dst_schema || '.')
               )
           ), '{}'::jsonb[])
    INTO rule_objects
    FROM pg_rules
    WHERE schemaname = source_schema;

    IF _verbose THEN
        RAISE INFO '    Got %s rule objects...', cardinality(rule_objects);
    END IF;

    /* Comment objects */
    IF _verbose THEN
        RAISE INFO 'Gathering object comment data from %...', source_schema;
    END IF;

    select coalesce(array_agg(
               jsonb_build_object(
                   'oid', t.oid,
                   'attnum', coalesce(c.attnum, -1),
                   'relkind', t.relkind,
                   'table_name', quote_ident(t.relname::text),
                   'dot', case when c.attname is not null then '.' else '' end::text,
                   'column_name', case when c.attname is not null then quote_ident(c.attname) else '' end::text,
                   'comment_type', case when c.attname is null
                                             then case t.relkind
                                                       when 'm' then 'MATERIALIZED VIEW'
                                                       when 'v' then 'VIEW'
                                                       else 'TABLE'
                                                  end::text
                                        else 'COLUMN'
                                   end::text,
                   'description', d.description
               )
               order by t.oid, coalesce(c.attnum, -1)
           ), '{}'::jsonb[])
      into comment_objects
      from pg_description d
      join pg_class t
        on t.oid = d.objoid
      left
      join pg_attribute c
        on c.attrelid = t.oid
       and c.attnum = d.objsubid
     where t.relnamespace = source_schema::regnamespace
       and t.relkind = any('{r,p,v,m}'::text[]);

    IF _verbose THEN
        RAISE INFO '    Got %s comment objects...', cardinality(comment_objects);
    END IF;

    /*
     * ======================================================================
     */

    /*
     * Create the new schema
     */
    IF _verbose
    THEN
        RAISE INFO 'Creating schema %', dst_schema;
    END IF;
    EXECUTE 'CREATE SCHEMA ' || dst_schema || ' ;';

    /*
     * Create tables
     */
    IF cardinality(table_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Creating tables for %', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY table_objects
        LOOP
            dest_obj = dst_schema || '.' || quote_ident(jobject->>'table_name'::text);
            source_obj = src_schema || '.' || quote_ident(jobject->>'table_name'::text);

            IF jobject->>'table_kind' = 'p'::text
            THEN
                IF _verbose
                THEN
                    RAISE INFO '    % (partitioned table)', dest_obj;
                END IF;
                EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %s (LIKE %s INCLUDING ALL) PARTITION BY %s ( %I ) ;',
                            dest_obj,
                            source_obj,
                            jobject->>'partition_type'::text,
                            jobject->>'partition_key'::text);
            ELSIF (jobject->>'is_partition'::text):: boolean
            THEN
                IF _verbose
                THEN
                    RAISE INFO '    % (table partition)', dest_obj;
                END IF;
                EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %s PARTITION OF %s.%I %s ;',
                            dest_obj,
                            dst_schema,
                            jobject->>'partitioned_table'::text,
                            jobject->>'partition_expr'::text);
            ELSE
                IF _verbose
                THEN
                    RAISE INFO '    % (table)', dest_obj;
                END IF;
                EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %s (LIKE %s INCLUDING ALL) ;',
                            dest_obj,
                            source_obj);
            END IF;

            IF (copy_data OR
                (jobject->>'table_name' ~ 'partitioned_tables'::text) OR
                (jobject->>'table_name' ~ 'django_migrations'::text)) AND
            (jobject->>'table_kind' = 'r'::text)
            THEN
                IF _verbose
                THEN
                    RAISE INFO '        Copying data...';
                END IF;
                EXECUTE FORMAT('INSERT INTO %s SELECT * FROM %s ;',
                            dest_obj,
                            source_obj);
            END IF;

            IF jobject->>'table_name' = 'partitioned_tables'::text
            THEN
                IF _verbose
                THEN
                    RAISE INFO '        Update partitioned_tables schema data';
                END IF;
                EXECUTE FORMAT('UPDATE %s SET schema_name = %L ;',
                            dest_obj,
                            dest_schema);
            END IF;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No tables for %', dst_schema;
        END IF;
    END IF;

    /*
     * Set sequence value
     */
    IF cardinality(sequence_owner_info) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Set current value for sequence objects in %', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY sequence_owner_info
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    Update sequence value for %.%', dst_schema, quote_ident(jobject->>'owner_object'::text);
            END IF;

            EXECUTE FORMAT('SELECT setval(''%s.%I'', (SELECT max(%I) FROM %s.%I));',
                        dst_schema,
                        jobject->>'sequence_name'::text,
                        jobject->>'owner_column'::text,
                        dst_schema,
                        jobject->>'owner_object'::text);
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No sequence owner data for %', dst_schema;
        END IF;
    END IF;

    /*
     * Create Foreign Key Constraints
     */
    IF cardinality(fk_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Create foriegn key constraints for tables in "%"', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY fk_objects
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    %.%', jobject->>'table_name', jobject->>'constraint_name'::text;
            END IF;
            EXECUTE jobject->>'alter_stmt'::text;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No foreign key constraints for %', dst_schema;
        END IF;
    END IF;

    /*
     * Create Views
     */
    IF cardinality(view_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Creating views for %', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY view_objects
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    %: "%"', jobject->>'view_kind', jobject->>'view_name'::text;
            END IF;
            EXECUTE FORMAT('CREATE %s %s.%I AS %s',
                        jobject->>'view_kind'::text,
                        dst_schema,
                        jobject->>'view_name'::text,
                        jobject->>'view_def'::text);

            IF jsonb_array_length(jobject->'view_indexes') > 0
            THEN
                IF _verbose
                THEN
                    RAISE INFO '        Create indexes';
                END IF;
                FOR ix_stmt IN select jsonb_array_elements_text(jobject->'view_indexes')
                LOOP
                    EXECUTE ix_stmt;
                END LOOP;
            END IF;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No view objects for %', dst_schema;
        END IF;
    END IF;

    /*
     * Create functions
     */
    IF cardinality(function_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Create functions, procedures for "%"', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY function_objects
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    "%" "%"', jobject->>'func_type', jobject->>'func_name'::text;
            END IF;
            EXECUTE jobject->>'func_stmt'::text;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No function/procedure objects for %', dst_schema;
        END IF;
    END IF;

    /*
     * Create triggers
     */
    IF cardinality(trigger_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Create triggers on objects in "%"', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY trigger_objects
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    "%"."%"', jobject->>'table_name', jobject->>'trigger_name'::text;
            END IF;
            EXECUTE jobject->>'trigger_def'::text;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No trigger objects for %', dst_schema;
        END IF;
    END IF;

    /*
     *  Create rules
     */
    IF cardinality(rule_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Creating rules on objects in %', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY rule_objects
        LOOP
            IF _verbose
            THEN
                RAISE INFO '    RULE "%" on "%"', jobject->>'rulename', jobject->>'tablename'::text;
            END IF;
            EXECUTE jobject->>'rule_def'::text;
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No rule objects for %', dst_schema;
        END IF;
    END IF;

    /*
     * Create comments
     */
    IF cardinality(comment_objects) > 0
    THEN
        IF _verbose
        THEN
            RAISE INFO 'Creating comments on objects in %', dst_schema;
        END IF;
        FOREACH jobject IN ARRAY comment_objects
        LOOP
            IF _verbose AND ((jobject->>'attnum')::int = -1)
            THEN
                RAISE INFO '    % % %', jobject->>'comment_type', jobject->>'table_name', jobject->>'column_name';
            END IF;
            EXECUTE FORMAT('COMMENT ON %s %s.%s%s%s IS %L ;',
                        jobject->>'comment_type'::text,
                        dst_schema,
                        jobject->>'table_name',
                        jobject->>'dot',
                        jobject->>'column_name'::text,
                        jobject->>'description'::text);
        END LOOP;
    ELSE
        IF _verbose
        THEN
            RAISE INFO 'No comments on objects for %', dst_schema;
        END IF;
    END IF;

    RETURN true;
END;
$$ LANGUAGE plpgsql;
