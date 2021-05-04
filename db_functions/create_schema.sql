/*
Copyright 2021 Red Hat, Inc.

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

DROP FUNCTION IF EXISTS public.create_schema(text, jsonb, text[], boolean, boolean);
CREATE OR REPLACE FUNCTION public.create_schema(
    source_schema text,
    source_structure jsonb,
    new_schemata text[],
    copy_data boolean DEFAULT false,
    _verbose boolean DEFAULT false
) RETURNS text[] AS $$
DECLARE
    jobject jsonb;
    dest_schema text;
    src_schema text;
    dst_schema text;
    dest_obj text;
    ix_stmt text;
    seq_start int;
    dest_schema_exists oid;
    completed_schemata text[];
BEGIN
    FOREACH dest_schema IN ARRAY new_schemata
    LOOP
        dst_schema = quote_ident(dest_schema);
        src_schema = quote_ident(source_schema);

        /* Check if dest schema exists */
        SELECT oid
          INTO dest_schema_exists
          FROM pg_namespace
         WHERE nspname = dest_schema;
        IF dest_schema_exists IS NOT NULL
        THEN
            if _verbose
            THEN
                RAISE INFO 'Destination schema % already exists.', dst_schema;
            END IF;

            completed_schemata = array_append(completed_schemata, '!' || dest_schema);
        END IF;

        CONTINUE WHEN dest_schema_exists IS NOT NULL;

        /*
         * Create the new schema
         */
        IF _verbose
        THEN
            RAISE INFO 'Creating schema %', dst_schema;
        END IF;
        EXECUTE FORMAT('CREATE SCHEMA %I ;', dest_schema);

        EXECUTE FORMAT('SET LOCAL search_path = %I, public ;', dest_schema);

        /*
         * Create sequences
         */

        IF jsonb_array_length(source_structure->'sequence_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Creating sequences for %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'sequence_data')
            LOOP
                IF _verbose
                THEN
                    RAISE INFO '    %.%', dst_schema, quote_ident(jobject->>'sequence_name');
                END IF;

                IF copy_data OR
                   (jobject->>'sequence_name' ~ 'partitioned_tables'::text) OR
                   (jobject->>'sequence_name' ~ 'django_migrations'::text)
                THEN
                    seq_start = coalesce((jobject->>'sequence_last_value')::bigint + 1, (jobject->>'sequence_start')::bigint);
                END IF;

                EXECUTE FORMAT('CREATE SEQUENCE IF NOT EXISTS %I AS %s START WITH %s INCREMENT BY %s MINVALUE %s MAXVALUE %s CACHE %s %s ;',
                            jobject->>'sequence_name'::text,
                            jobject->>'sequence_type'::text,
                            seq_start::bigint,
                            (jobject->>'sequence_inc')::bigint,
                            (jobject->>'sequence_min')::bigint,
                            (jobject->>'sequence_max')::bigint,
                            (jobject->>'sequence_cache')::bigint,
                            jobject->>'sequence_cycle'::text);
            END LOOP;
        ELSE
            IF _verbose
            THEN
                RAISE INFO 'No sequences for %', dst_schema;
            END IF;
        END IF;

        /*
         * Create tables
         */
        IF jsonb_array_length(source_structure->'table_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Creating tables for %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'table_data')
            LOOP
                dest_obj = dst_schema || '.' || quote_ident(jobject->>'table_name'::text);

                IF jobject->>'table_kind' = 'p'::text
                THEN
                    IF _verbose
                    THEN
                        RAISE INFO '    % (partitioned table)', dest_obj;
                    END IF;
                    EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %I (LIKE %I.%I INCLUDING ALL) PARTITION BY %s ( %I ) ;',
                                jobject->>'table_name'::text,
                                source_schema,
                                jobject->>'table_name'::text,
                                jobject->>'partition_type'::text,
                                jobject->>'partition_key'::text);
                ELSIF (jobject->>'is_partition'::text):: boolean
                THEN
                    IF _verbose
                    THEN
                        RAISE INFO '    % (table partition)', dest_obj;
                    END IF;
                    EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %I PARTITION OF %I %s ;',
                                jobject->>'table_name'::text,
                                jobject->>'partitioned_table'::text,
                                jobject->>'partition_expr'::text);
                ELSE
                    IF _verbose
                    THEN
                        RAISE INFO '    % (table)', dest_obj;
                    END IF;
                    EXECUTE FORMAT('CREATE TABLE IF NOT EXISTS %I (LIKE %I.%I INCLUDING ALL) ;',
                                jobject->>'table_name'::text,
                                source_schema,
                                jobject->>'table_name'::text);
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
                    EXECUTE FORMAT('INSERT INTO %I SELECT * FROM %I.%I ;',
                                jobject->>'table_name'::text,
                                source_schema,
                                jobject->>'table_name'::text);
                END IF;

                IF jobject->>'table_name' = 'partitioned_tables'::text
                THEN
                    IF _verbose
                    THEN
                        RAISE INFO '        Update partitioned_tables schema data';
                    END IF;
                    EXECUTE 'UPDATE partitioned_tables SET schema_name = current_schema ;';
                END IF;
            END LOOP;
        ELSE
            IF _verbose
            THEN
                RAISE INFO 'No tables for %', dst_schema;
            END IF;
        END IF;

        /*
         * Create sequence owner links
         */
        IF jsonb_array_length(source_structure->'sequence_owner_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Setting sequence ownership for objects in %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'sequence_owner_data')
            LOOP
                IF _verbose
                THEN
                    RAISE INFO '    Update primary key default for %.%', dst_schema, quote_ident(jobject->>'owner_object'::text);
                END IF;
                EXECUTE FORMAT('ALTER TABLE %I ALTER COLUMN %I SET DEFAULT nextval( ''%I''::regclass );',
                            jobject->>'owner_object'::text,
                            jobject->>'owner_column'::text,
                            jobject->>'sequence_name'::text);

                IF _verbose
                THEN
                    RAISE INFO '    Update sequence owned-by table column to %."%"', dest_obj, jobject->>'owner_column'::text;
                END IF;
                EXECUTE FORMAT('ALTER SEQUENCE %I OWNED BY %I.%I ;',
                            jobject->>'sequence_name'::text,
                            jobject->>'owner_object'::text,
                            jobject->>'owner_column'::text);
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
        IF jsonb_array_length(source_structure->'foreign_key_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Create foriegn key constraints for tables in "%"', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'foreign_key_data')
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
        IF jsonb_array_length(source_structure->'view_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Creating views for %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'view_data')
            LOOP
                IF _verbose
                THEN
                    RAISE INFO '    %: "%"', jobject->>'view_kind', jobject->>'view_name'::text;
                END IF;
                EXECUTE FORMAT('CREATE %s %I AS %s',
                            jobject->>'view_kind'::text,
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
        IF jsonb_array_length(source_structure->'function_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Create functions, procedures for "%"', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'function_data')
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
        IF jsonb_array_length(source_structure->'trigger_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Create triggers on objects in "%"', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'trigger_data')
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
        IF jsonb_array_length(source_structure->'rule_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Creating rules on objects in %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'rule_data')
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
        IF jsonb_array_length(source_structure->'comment_data') > 0
        THEN
            IF _verbose
            THEN
                RAISE INFO 'Creating comments on objects in %', dst_schema;
            END IF;
            FOR jobject IN SELECT jsonb_array_elements(source_structure->'comment_data')
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

        /*
         * Mark that the dest_schema object creation has been successful
         */
        completed_schemata = array_append(completed_schemata, '+' || dest_schema);
    END LOOP; -- new schema loop end

    RETURN completed_schemata;
END;
$$ LANGUAGE plpgsql;
