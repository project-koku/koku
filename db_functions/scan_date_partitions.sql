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
-- Function to return table partition start bounds from scanning another table for partition key values.
-- Args:
--   check_table (text)      : Name of the table to check for partition start bounds
--   check_col (text)        : Name of the column that holds the date values to check
--   schema (text)           : Schema of the partitioned table
--   parttioned_table (text) : Name of the partitioned table within the schema
DROP FUNCTION IF EXISTS public.scan_for_date_partitions(text, text, text, text);
CREATE OR REPLACE FUNCTION public.scan_for_date_partitions(
    check_table text,
    check_col text,
    schema text,
    partitioned_table text
)
RETURNS TABLE (partition_start date)
AS $$
DECLARE
    rec record;
    table_parts text[];
    check_table_name text;
    partition_name text  = '';
    check_stmt text = '';
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
                    '       date_trunc(''month'', ' || quote_ident(check_col) || ')::date as date_val,' ||
                    '       to_char(' || quote_ident(check_col) || ', ''YYYY-MM-01'')::text as date_key' ||
                    '  FROM ' || check_table_name || ' ' ||
                    ') ' ||
                    'SELECT ddk.date_val as partition_start ' ||
                    '  FROM distinct_date_key as ddk ' ||
                    ' WHERE NOT EXISTS (SELECT 1 ' ||
                    '                     FROM ' ||
                                            quote_ident(schema) || '."partitioned_tables" ' ||
                    '                    WHERE schema_name = ' || quote_literal(schema) ||
                    '                      AND partition_of_table_name = ' || quote_literal(partitioned_table) ||
                    '                      AND partition_type = ''range'' ' ||
                    '                      AND ddk.date_key = (partition_parameters->>''from'') ) ;';
    RETURN QUERY EXECUTE check_stmt;
END;
$$
LANGUAGE plpgsql;
