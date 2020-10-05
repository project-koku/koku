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
--   _commit (boolean)       : Execute a commit after action. (default is false)
DROP PROCEDURE IF EXISTS public.create_table_date_range_partition( text, text, text, date, date, boolean, boolean );
CREATE OR REPLACE PROCEDURE public.create_table_date_range_partition(
    schema text,
    table_partition text,
    partitioned_table text,
    date_from date,
    date_to date,
    _default boolean DEFAULT false,
    _commit boolean DEFAULT false
) AS $$
DECLARE
    action_stmt text = '';
    end_date date = null::date;
BEGIN
    IF ( schema IS NULL OR schema = '' )
    THEN
        RAISE null_value_not_allowed
              USING MESSAGE = 'schema parameter cannot be null or empty string',
                    HINT = 'Use a valid schema name.';
    END IF;
    IF ( table_partition IS NULL OR table_partition = '' )
    THEN
        RAISE null_value_not_allowed
              USING MESSAGE = 'table_partition parameter cannot be null or empty string',
                    HINT = 'This must be a unique table name within the specified schema.';
    END IF;
    IF ( partitioned_table IS NULL OR partitioned_table = '' )
    THEN
        RAISE null_value_not_allowed
              USING MESSAGE = 'partitioned_table parameter cannot be null or empty string',
                    HINT = 'This must be the name of a table within the specified schema that is a partitioned table.';
    END IF;
    if ( NOT _default )
    THEN
        IF ( date_from IS NULL )
        THEN
            RAISE null_value_not_allowed
                USING MESSAGE = 'date_from parameter cannot be null',
                        HINT = 'This should be a valid date.';
        END IF;
        IF ( date_to IS NULL )
        THEN
            end_date = (date_from::date + '1 month'::interval)::date;
        ELSE
            end_date = date_to;
        END IF;
    END IF;

    action_stmt = 'CREATE TABLE IF NOT EXISTS ' ||
                    quote_ident(schema) || '.' || quote_ident(table_partition) ||
                    ' PARTITION OF ' ||
                    quote_ident(schema) || '.' || quote_ident(partitioned_table);
    IF ( _default )
    THEN
        action_stmt = action_stmt ||
                    ' DEFAULT ; ';
    ELSE
        action_stmt = action_stmt ||
                    ' FOR VALUES FROM (' ||
                    quote_literal(date_from) ||
                    '::date) TO (' ||
                    quote_literal(end_date) ||
                    '::date); ';
    END IF;
    EXECUTE action_stmt;

    -- log the new partition
    action_stmt = 'INSERT INTO ' || quote_ident(schema) || '."partitioned_tables" ( ' ||
                          '"schema_name", "table_name", "partition_of_table_name", ' ||
                          '"partition_type", "partition_col", "partition_parameters" ' ||
                  ') ' ||
                  'SELECT ' || quote_literal(schema) || ', ' ||
                               quote_literal(table_partition) || ', ' ||
                               quote_literal(partitioned_table) || ', ' ||
                               '''range'', ' ||
                               'string_agg(a.attname, '',''), ' ||
                               'jsonb_build_object( ' ||
                                   '''default'', false, ' ||
                                   '''from'', ' || quote_literal(date_from::text) || ', ' ||
                                   '''to'', ' || quote_literal(end_date::text) ||
                               ') ' ||
                    'FROM pg_partitioned_table p ' ||
                    'JOIN pg_attribute a ' ||
                      'ON a.attrelid = p.partrelid ' ||
                     'AND a.attnum = any(string_to_array(p.partattrs::text, '' '')::smallint[]) ' ||
                   'WHERE p.partrelid = ' ||
                          quote_literal(schema || '.'::text || partitioned_table) || '::regclass ' ||
                      'ON CONFLICT (schema_name, table_name) DO NOTHING ;';
    EXECUTE action_stmt;

    IF ( _commit = true )
    THEN
        COMMIT;
    END IF;
END;
$$
LANGUAGE plpgsql;
