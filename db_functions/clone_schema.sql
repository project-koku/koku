-- Function: clone_schema(text, text)

-- DROP FUNCTION clone_schema(text, text);

CREATE OR REPLACE FUNCTION public.clone_schema(
    source_schema text,
    dest_schema text,
    include_recs boolean DEFAULT false,
    add_tenant boolean DEFAULT true,
    _verbose boolean DEFAULT false)
  RETURNS boolean AS
$BODY$

--  This function will clone all sequences, tables, data, views & functions from any existing schema to a new one
-- SAMPLE CALL:
-- SELECT clone_schema('public', 'new_schema', TRUE);

DECLARE
  object_rec       record;
  object2_rec      record;
  source_obj       text;
  dest_obj         text;
  seqval           bigint;

BEGIN

  -- Check that source_schema exists
  PERFORM oid
    FROM pg_namespace
   WHERE nspname = quote_ident(source_schema);
  IF NOT FOUND
    THEN
    RAISE NOTICE 'source schema % does not exist!', source_schema;
    RETURN false;
  END IF;

  SET LOCAL search_path = source_schema;

  -- Check that dest_schema does not yet exist
  PERFORM nspname
    FROM pg_namespace
   WHERE nspname = quote_ident(dest_schema);
  IF FOUND
    THEN
    RAISE NOTICE 'dest schema % already exists!', dest_schema;
    RETURN false;
  END IF;

  IF _verbose
  THEN
    RAISE NOTICE 'Creating schema %', dest_schema;
  END IF;
  EXECUTE 'CREATE SCHEMA ' || quote_ident(dest_schema) ;

  -- Create sequences
  -- TODO: Find a way to make this sequence's owner is the correct table.
  IF _verbose
  THEN
    RAISE NOTICE 'Creating sequences:';
  END IF;
  FOR object_rec IN
    SELECT c.relname as "sequence_name",
           s.seqtypid::regtype::text as "sequence_type",
           s.seqstart as "sequence_start",
           s.seqincrement as "sequence_inc",
           s.seqmax as "sequence_max",
           s.seqmin as "sequence_min",
           s.seqcache as "sequence_cache",
           case when s.seqcycle then 'CYCLE' else 'NO CYCLE' end::text as "sequence_cycle"
      FROM pg_sequence s
      JOIN pg_class c
        ON c.oid = s.seqrelid
       AND c.relnamespace = source_schema::regnamespace
  LOOP

    IF _verbose
    THEN
      RAISE NOTICE '    %s.%s', quote_ident(dest_schema), quote_ident(object_rec.sequence_name);
    END IF;
    EXECUTE 'CREATE SEQUENCE IF NOT EXISTS ' ||
            quote_ident(dest_schema) || '.' || quote_ident(object_rec.sequence_name) ||
            ' AS ' || object_rec.sequence_type ||
            ' INCREMENT BY ' || object_rec.sequence_inc ||
            ' MINVALUE ' || object_rec.sequence_min ||
            ' MAXVALUE ' || object_rec.sequence_max ||
            ' START WITH ' || object_rec.sequence_start ||
            ' CACHE ' || object_rec.sequence_cache ||
            ' ' || object_rec.sequence_cycle || ' ;';

    IF include_recs or
       (object_rec.sequence_name ~ 'partitioned_tables') or
       (object_rec.sequence_name ~ 'django_migrations')
    THEN
        EXECUTE 'SELECT setval( ''' || quote_ident(dest_schema) || '.' || quote_ident(object_rec.sequence_name) ||
                '''::regclass, (SELECT last_value + 1 from ' ||
                quote_ident(source_schema) || '.' || quote_ident(object_rec.sequence_name) || ') ) ;' ;
    END IF;

  END LOOP;

  -- Create tables
  IF _verbose
  THEN
    RAISE NOTICE 'Creating tables:';
  END IF;
  FOR object_rec IN
    SELECT t.oid::bigint as "obj_id",
           t.relname::text as "table_name",
           t.relkind::text as "table_kind",
           CASE pt2.partstrat
                WHEN 'h' THEN 'HASH'
                WHEN 'l' THEN 'LIST'
                WHEN 'r' THEN 'RANGE'
                ELSE null
           END::text as "partition_type",
           pk.attname as "partition_key",
           t.relispartition as "is_partition",
           p.relname as "partitioned_table",
           pg_get_expr(t.relpartbound, t.oid)::text as "partition_expr"
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
        BY case t.relkind
                when 'p' then 0
                else 1
           end::int,
           t.relispartition
  LOOP
    dest_obj := quote_ident(dest_schema) || '.' || quote_ident( object_rec.table_name);
    source_obj := quote_ident(source_schema) || '.' || quote_ident( object_rec.table_name);
    IF  object_rec.table_kind = 'p'
    THEN
        IF _verbose
        THEN
          RAISE NOTICE '    % (partitioned table)', dest_obj;
        END IF;
        EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' (LIKE ' || source_obj || ' INCLUDING ALL)' ||
                'PARTITION BY ' ||  object_rec.partition_type ||
                ' ( ' || quote_ident( object_rec.partition_key) || ' ) ;';
    ELSIF  object_rec.is_partition
    THEN
        source_obj := quote_ident(dest_schema) || '.' || quote_ident( object_rec.partitioned_table);
        IF _verbose
        THEN
          RAISE NOTICE '    % (table partition)', dest_obj;
        END IF;
        EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' PARTITION OF ' || source_obj || ' ' ||
                 object_rec.partition_expr || ' ;';
    ELSE
        IF _verbose
        THEN
          RAISE NOTICE '    % (table)', dest_obj;
        END IF;
        EXECUTE 'CREATE TABLE IF NOT EXISTS ' || dest_obj || ' (LIKE ' || source_obj || ' INCLUDING ALL)';
    END IF;

    IF include_recs or
       (object_rec.table_name = 'partitioned_tables') or
       (object_rec.table_name = 'django_migrations')
    THEN
      -- Insert records from source table
      IF _verbose
      THEN
        RAISE NOTICE '        Copy data...';
      END IF;
      EXECUTE 'INSERT INTO ' || dest_obj || ' SELECT * FROM ' || source_obj || ';';

      IF object_rec.table_name = 'partitioned_tables'
      THEN
        IF _verbose
        THEN
          RAISE NOTICE '        Update partition tracker schema name...';
        END IF;
        EXECUTE 'UPDATE ' || dest_obj || ' SET schema_name = ' || quote_literal(dest_schema) || ' ;';
      END IF;
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
          RAISE NOTICE '        Update primary key default';
        END IF;
        EXECUTE 'ALTER TABLE ' || dest_obj || ' ALTER COLUMN ' || object2_rec.owner_column ||
                ' SET DEFAULT nextval(''' || dest_schema || '.' || object2_rec.sequence_name || '''::regclass) ;';
        IF _verbose
        THEN
          RAISE NOTICE '        Update sequence owner';
        END IF;
        EXECUTE 'ALTER SEQUENCE ' || dest_schema || '.' || object2_rec.sequence_name ||
                ' OWNED BY ' || dest_obj || '.' || object2_rec.owner_column || ' ;';
      END LOOP;
    END IF;

  END LOOP;


  --  add FK constraint
  IF _verbose
  THEN
    RAISE NOTICE 'Creating Foreign Key constraints:';
  END IF;
  FOR object_rec IN
    SELECT rn.relname,
           ct.conname,
           'ALTER TABLE ' || quote_ident(dest_schema) || '.' || quote_ident(rn.relname)
                          || ' ADD CONSTRAINT ' || quote_ident(ct.conname) ||
                          ' ' || pg_get_constraintdef(ct.oid) || ';' as query
      FROM pg_constraint ct
      JOIN pg_class rn
        ON rn.oid = ct.conrelid
     WHERE connamespace = source_schema::regnamespace
       AND rn.relkind = 'r'
       AND ct.contype = 'f'

    LOOP
      IF _verbose
      THEN
        RAISE NOTICE '    %.%', object_rec.relname, object_rec.conname;
      END IF;
      EXECUTE object_rec.query;

    END LOOP;


  -- Create views
  IF _verbose
  THEN
    RAISE NOTICE 'Creating views:';
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
           replace(pg_get_viewdef(view_oid), source_schema || '.', dest_schema || '.') as "view_def"
      FROM view_deps
    )
    SELECT view_name,
           CASE WHEN view_kind = 'm'
                     THEN 'MATERIALIZED'
                ELSE ''
           END::text as view_kind,
           CASE WHEN view_kind = 'm'
                     THEN substr(view_def, 1, length(view_def) - 1) || ' WITH DATA;'
                ELSE view_def
           END::text as "view_def"
      FROM base_view_def
     ORDER
        BY depth
  LOOP
    IF _verbose
    THEN
      RAISE NOTICE '    % view %', object_rec.view_kind, quote_ident(dest_schema) || '.' || quote_ident(object_rec.view_name);
    END IF;
    EXECUTE 'CREATE ' || object_rec.view_kind || ' VIEW ' ||
            quote_ident(dest_schema) || '.' || quote_ident(object_rec.view_name) || ' AS ' ||
            object_rec.view_def;
  END LOOP;


  -- Create functions
  IF _verbose
  THEN
    RAISE NOTICE 'Creating functions:';
  END IF;
  FOR object_rec IN
    SELECT proname,
           replace(pg_get_functiondef(oid), source_schema, dest_schema) as "qry"
      FROM pg_proc
     WHERE pronamespace = source_schema::regnamespace
  LOOP
    IF _verbose
    THEN
      RAISE NOTICE '    %.%', dest_schema, object_rec.proname;
    END IF;
    EXECUTE object_rec.qry;

  END LOOP;


  -- Create triggers
  IF _verbose
  THEN
    RAISE NOTICE 'Creating triggers:';
  END IF;
  FOR object_rec IN
    SELECT t.oid as trigger_id,
           t.tgname::text as trigger_name,
           c.relname as trigger_table,
           replace(pg_get_triggerdef(t.oid), source_schema || '.', dest_schema || '.') as trigger_def
      FROM pg_trigger t
      JOIN pg_class c
        ON c.oid = t.tgrelid
     WHERE c.relnamespace = source_schema::regnamespace
       AND t.tgconstraint = 0
  LOOP
    IF _verbose
    THEN
      RAISE NOTICE '    %.%', object_rec.trigger_table, object_rec.trigger_name;
    END IF;
    EXECUTE object_rec.trigger_def;
  END LOOP;

  IF add_tenant
  THEN
    IF _verbose
    THEN
      RAISE NOTICE 'Adding tenant % to tenant tracker', dest_schema;
    END IF;
    INSERT INTO public.api_tenant (schema_name)
    VALUES (dest_schema)
        ON CONFLICT (schema_name) DO NOTHING;
  END IF;

  RETURN true;

END;

$BODY$
  LANGUAGE plpgsql VOLATILE
  COST 100;


/*
ALTER FUNCTION clone_schema(text, text, boolean)
  OWNER TO postgres;
*/
