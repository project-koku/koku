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
DROP FUNCTION IF EXISTS public.app_migration_check(jsonb, boolean);

CREATE OR REPLACE FUNCTION public.app_needs_migrations(leaf_migrations jsonb, _verbose boolean DEFAULT false)
RETURNS boolean AS $BODY$
DECLARE
    schema_rec record;
    leaf_app_key text;
    leaf_app_keys text[];
    latest_migrations jsonb;
    do_migrations boolean := false;
BEGIN
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
