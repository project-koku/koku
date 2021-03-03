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
-- Function public.app_needs_migrations(leaf_migrations, _verbose)
-- Returns bool: true = run migrations; false = migrations up-to-date
-- leaf_migrations (jsonb) = leaf migration names by app from the django code
--    Ex: '{<django-app>: <latest-leaf-migration-name>}'
-- Set _verbose to true to see notices raised during execution
DROP FUNCTION IF EXISTS public.app_needs_migrations(jsonb, boolean);

CREATE OR REPLACE FUNCTION public.app_needs_migrations(leaf_migrations jsonb, _verbose boolean DEFAULT false)
RETURNS boolean AS $BODY$
DECLARE
    schema_rec record;
    leaf_app_key text;
    leaf_app_keys text[];
    latest_migrations jsonb;
    required_tables int := 0;
    do_migrations boolean := false;
    objects_exist boolean := false;
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
        RETURN true;
    END IF;

    /*
     * setup app keys for processing
     */
    SELECT array_agg(k)
      INTO leaf_app_keys
      FROM jsonb_object_keys(leaf_migrations) k;

    FOR schema_rec IN
        SELECT t.schema_name
          FROM public.api_tenant t
          JOIN pg_namespace n
            on n.nspname = t.schema_name
         ORDER
            BY case when schema_name = 'public'
                         then '0public'
                    else schema_name
               END::text
    LOOP
        /* Check for race condition if someone deletes a source, etc during processing */
        SELECT EXISTS (
                        SELECT c.oid
                          FROM pg_class c
                          JOIN pg_namespace n
                            ON n.oid = c.relnamespace
                         WHERE c.relname = 'django_migrations'
                           AND n.nspname = schema_rec.schema_name
                      )::boolean
          INTO objects_exist;

        IF NOT objects_exist
        THEN
            RAISE WARNING 'Object %.% does not exist. Skipping schema %',
                          schema_rec.schema_name,
                          'django_migrations',
                          schema_rec.schema_name;
        END IF;

        CONTINUE WHEN NOT objects_exist;

        /* Get the latest recorded migrations by app for this tenant schema */
        IF _verbose
        THEN
            RAISE NOTICE 'Checking %', schema_rec.schema_name;
        END IF;
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
                IF _verbose
                THEN
                    RAISE NOTICE '    checking %.% > %.%',
                                 leaf_app_key,
                                 leaf_migrations->>leaf_app_key,
                                 leaf_app_key,
                                 latest_migrations->>leaf_app_key;
                END IF;
                IF leaf_migrations->>leaf_app_key > latest_migrations->>leaf_app_key
                THEN
                    /* leaf ahead of last recorded. run migrations! */
                    do_migrations = true;
                    EXIT;
                END IF;
            ELSE
                /* App does not exist, run migrations! */
                IF _verbose
                THEN
                    RAISE NOTICE '    app % missing from schema', leaf_app_key;
                END IF;
                do_migrations = true;
                EXIT;
            END IF;
        END LOOP;

        /* Stop processing if we are going to run migrations */
        EXIT WHEN do_migrations;
    END LOOP;

    RETURN do_migrations;
END;
$BODY$ LANGUAGE PLPGSQL;
