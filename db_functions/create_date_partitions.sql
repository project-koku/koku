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
-- Procedure to create table partitions.
-- Depends on the partitioned_tables table being defined in each schema
-- Args:
--   check_table (text)      : Name of the table to check for partition start bounds
--   check_col (text)        : Name of the column that holds the date values to check
--   schema (text)           : Schema of the partitioned table
--   parttioned_table (text) : Name of the partitioned table within the schema
--   partition_key (text)    : Partition key (column) name
--   _commit (boolean)       : Execute a commit after action. (default is false)
DROP PROCEDURE IF EXISTS public.create_date_partitions(text, text, text, text, text, boolean);
CREATE OR REPLACE PROCEDURE public.create_date_partitions(
    check_table text,
    check_col text,
    schema text,
    partitioned_table text,
    partition_key text,
    _commit boolean DEFAULT false
) AS $$
DECLARE
    rec record;
    table_parts text[];
    check_table_name text;
    partition_name text  = '';
    check_stmt text = '';
    action_stmt text = '';
BEGIN
    table_parts = string_to_array(check_table, '.');
    IF ( cardinality(table_parts) > 1 )
    THEN
        check_table_name = quote_ident(table_parts[1]) || '.'::text || quote_ident(table_parts[2]);
    ELSE
        check_table_name = quote_ident(table_parts[1]);
    END IF;

    check_stmt = 'WITH distinct_date_key as (' ||
                    'SELECT DISTINCT ' ||
                    '       to_char(' || quote_ident(check_col) || ', ''YYYY-MM-01'')::text as date_key' ||
                    '  FROM ' || check_table_name || ' ' ||
                    ') ' ||
                    'SELECT ddk.date_key::date' ||
                    '  FROM distinct_date_key as ddk ' ||
                    ' WHERE NOT EXISTS (SELECT 1 ' ||
                    '                     FROM ' ||
                                            quote_ident(schema) || '."partitioned_tables" ' ||
                    '                    WHERE schema_name = ' || quote_literal(schema) ||
                    '                      AND partition_of_table_name = ' || quote_literal(partitioned_table) ||
                    '                      AND partition_type = ''range'' ' ||
                    '                      AND ddk.date_key = (partition_parameters->>''from'') ) ;';
    FOR rec IN EXECUTE check_stmt
    LOOP
        -- Create the new partition
        partition_name = partitioned_table || '_' || to_char(rec.date_key, 'YYYY_MM');

        action_stmt = 'CREATE TABLE ' ||
                        quote_ident(schema) || '.' || quote_ident(partition_name) ||
                        ' PARTITION OF ' ||
                        quote_ident(schema) || '.' || quote_ident(partitioned_table) ||
                        ' FOR VALUES FROM (' ||
                        quote_literal(rec.date_key) ||
                        '::date) TO (' ||
                        quote_literal((rec.date_key + '1 month'::interval)::date) ||
                        '::date); ';
        EXECUTE action_stmt;

        -- log the new partition
        action_stmt = 'INSERT INTO ' || quote_ident(schema) || '."partitioned_tables" ( ' ||
                        '    "schema_name", "table_name", "partition_of_table_name", ' ||
                        '    "partition_type", "partition_col", "partition_parameters" ' ||
                        ') VALUES ( ' ||
                            quote_literal(schema) || ', ' ||
                            quote_literal(partition_name) || ', ' ||
                            quote_literal(partitioned_table) || ', ' ||
                            quote_literal('range') || ' ,' ||
                            quote_literal(partition_key) || ', ' ||
                            'jsonb_build_object( ' ||
                            '    ''default'', false, ' ||
                            '    ''from'', ' || quote_literal(rec.date_key::text) || ', ' ||
                            '    ''to'', ' || quote_literal((rec.date_key + '1 month'::interval)::date::text) ||
                            ' ));';
        EXECUTE action_stmt;
        END LOOP;

    IF (_commit = true) AND (action_stmt != '')
    THEN
        COMMIT;
    END IF;
END;
$$ LANGUAGE PLPGSQL;
