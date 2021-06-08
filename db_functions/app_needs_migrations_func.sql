--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
-- Function public.app_needs_migrations(leaf_migrations, _verbose)
-- Returns bool: true = run migrations; false = migrations up-to-date
-- leaf_migrations (jsonb) = leaf migration names by app from the django code
--    Ex: '{<django-app>: <latest-leaf-migration-name>}'
-- Set _verbose to true to see notices raised during execution
DROP FUNCTION IF EXISTS public.migrations_complete(jsonb, boolean);

CREATE OR REPLACE FUNCTION public.migrations_complete(leaf_migrations jsonb, _verbose boolean DEFAULT false)
RETURNS boolean AS $BODY$
DECLARE
    schema_rec record;
    leaf_app_key text;
    leaf_app_keys text[];
    latest_migrations jsonb;
    required_tables int := 0;
    completed_migrations boolean := true;
    exists_rec record;
    chk_res boolean;
BEGIN
    /*
     * Verify that the necessary tables are present
     */
    SELECT count(*)
      INTO required_tables
      FROM pg_class c
      JOIN pg_namespace n
        ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname in ('api_tenant', 'django_migrations');

    /*
     * If migrations have been run against public, then we expect to find both tables
     */
    IF required_tables != 2
    THEN
        IF _verbose
        THEN
            RAISE WARNING 'Schema "public" not initialized';
        END IF;
        RETURN false;
    END IF;

    /*
     * setup app keys for processing
     */
    SELECT array_agg(k)
      INTO leaf_app_keys
      FROM jsonb_object_keys(leaf_migrations) k;

    FOR schema_rec IN
        SELECT nspname::text as schema_name
        FROM pg_catalog.pg_namespace
        WHERE nspname = 'public'
            OR nspname = 'template0'
            OR nspname LIKE 'acct%'
         ORDER
            BY case when nspname::text = 'public'
                         then '0public'
                    else nspname::text
               END::text
    LOOP
        /* Get the latest recorded migrations by app for this tenant schema */
        IF _verbose
        THEN
            RAISE INFO 'Checking migration state in schema %', schema_rec.schema_name;
        END IF;

        /* Check for race condition if someone deletes a source, etc during processing */
        EXECUTE 'SELECT EXISTS ( ' ||
                            'SELECT c.oid ' ||
                              'FROM pg_class c ' ||
                              'JOIN pg_namespace n ' ||
                                'ON n.oid = c.relnamespace ' ||
                             'WHERE c.relname = ''django_migrations'' ' ||
                               'AND n.nspname = ' || quote_literal(schema_rec.schema_name) || ' ' ||
                        ')::boolean as "objects_exist", ' ||
                        'EXISTS ( ' ||
                            'SELECT n.oid ' ||
                              'FROM pg_namespace n ' ||
                             'WHERE nspname = ' || quote_literal(schema_rec.schema_name) || ' ' ||
                        ')::boolean as "schema_exists" '
          INTO exists_rec;

        CONTINUE WHEN (NOT exists_rec.schema_exists);

        IF NOT exists_rec.objects_exist
        THEN
            RAISE WARNING '    %.django_migrations does not exist', schema_rec.schema_name;
            completed_migrations = false;
        ELSE
            EXECUTE 'SELECT jsonb_object_agg(app, migration) ' ||
                    'FROM ( ' ||
                            'SELECT app, ' ||
                                    'max(name) as "migration" ' ||
                            'FROM ' || quote_ident(schema_rec.schema_name) || '.django_migrations ' ||
                            'GROUP BY app ' ||
                        ') AS x ;'
            INTO latest_migrations;

            /* Loop through leaf apps */
            FOREACH leaf_app_key IN ARRAY leaf_app_keys
            LOOP
                /* test that app exists or not */
                IF latest_migrations ? leaf_app_key
                THEN
                    /* App exists! Test if the leaf migration name is greater than the last recorded migration for the app */
                    chk_res = (leaf_migrations->>leaf_app_key > latest_migrations->>leaf_app_key)::boolean;
                    IF _verbose
                    THEN
                        RAISE INFO '    checking %.% > %.% (%)',
                                    leaf_app_key,
                                    leaf_migrations->>leaf_app_key,
                                    leaf_app_key,
                                    latest_migrations->>leaf_app_key,
                                    chk_res::text;
                    END IF;
                    IF chk_res
                    THEN
                        /* leaf ahead of last recorded. run migrations! */
                        completed_migrations = false;
                        IF _verbose
                        THEN
                            RAISE INFO '        Will run migrations.';
                        END IF;
                    END IF;
                ELSE
                    /* App does not exist, run migrations! */
                    IF _verbose
                    THEN
                        RAISE INFO '    app % missing from schema', leaf_app_key;
                    END IF;
                    completed_migrations = false;
                END IF;

                EXIT WHEN not completed_migrations;
            END LOOP;
        END IF;

        /* Stop processing if we are going to run migrations */
        EXIT WHEN not completed_migrations;
    END LOOP;

    IF _verbose
    THEN
        RAISE INFO 'Migration Check: App should%execute migrations.', case when completed_migrations then ' not ' else ' ' end::text;
    END IF;

    RETURN completed_migrations;
END;
$BODY$ LANGUAGE PLPGSQL;
