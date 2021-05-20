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

-- This **WILL** drop the associated trigger!
DROP FUNCTION IF EXISTS public.trfn_partition_manager() CASCADE;
CREATE OR REPLACE FUNCTION public.trfn_partition_manager() RETURNS TRIGGER AS $$
DECLARE
    action_stmt text = '';
    action_stmt_2 text = '';
    action_ix integer = 1;
    total_actions integer = 0;
    action_stmts text[] = '{}'::text[];
    messages text[] = '{}'::text[];
    message_text text = '';
    col_type_name text = null;
BEGIN
    IF ( TG_OP = 'DELETE' )
    THEN
        IF ( OLD.active )
        THEN
            action_stmts = array_append(
                action_stmts,
                format(
                    'ALTER TABLE %I.%I DETACH PARTITION %I.%I ;',
                    OLD.schema_name,
                    OLD.partition_of_table_name,
                    OLD.schema_name,
                    OLD.table_name
                )
            );
            messages = array_append(
                messages,
                format(
                    'DETACH PARTITION %I.%I FROM %I.%I',
                    OLD.schema_name,
                    OLD.table_name,
                    OLD.schema_name,
                    OLD.partition_of_table_name
                )
            );
        END IF;
        action_stmts = array_append(
            action_stmts,
            format(
                'TRUNCATE TABLE %s ;', OLD.table_name
            )
        );
        messages = array_append(messages, format('TRUNCATE TABLE %I.%I', OLD.schema_name, OLD.table_name));
        action_stmts = array_append(
            action_stmts,
            format(
                'DROP TABLE %s ;', OLD.table_name
            )
        );
        messages = array_append(messages, format('DROP TABLE %I.%I', OLD.schema_name, OLD.table_name));
    ELSIF ( TG_OP = 'UPDATE' )
    THEN
        IF OLD.partition_of_table_name != NEW.partition_of_table_name
        THEN
            action_stmts = array_append(
                action_stmts,
                format(
                    'ALTER TABLE %I.%I RENAME TO %I ;',
                    OLD.schema_name,
                    OLD.partition_of_table_name,
                    NEW.partition_of_table_name
                )
            );
            messages = array_append(
                messages,
                format(
                    'RENAME TABLE %I.%I to %I',
                    OLD.schema_name,
                    OLD.partition_of_table_name,
                    NEW.partition_of_table_name
                )
            );
        END IF;

        IF OLD.table_name != NEW.table_name
        THEN
            action_stmts = array_append(
                action_stmts,
                format(
                    'ALTER TABLE %I.%I RENAME TO %I ;',
                    OLD.schema_name,
                    OLD.table_name,
                    NEW.table_name
                )
            );
            messages = array_append(
                messages,
                format(
                    'RENAME TABLE %I.%I to %I',
                    OLD.schema_name,
                    OLD.table_name,
                    NEW.table_name
                )
            );
        END IF;

        IF OLD.active AND NOT NEW.active
        THEN
            action_stmts = array_append(
                action_stmts,
                format(
                    'ALTER TABLE %I.%I DETACH PARTITION %I.%I ;',
                    OLD.schema_name,
                    NEW.partition_of_table_name,
                    OLD.schema_name,
                    NEW.table_name
                )
            );
            messages = array_append(
                messages,
                format('DETACH PARTITION %I.%I FROM %I.%I',
                    OLD.schema_name,
                    NEW.table_name,
                    OLD.schema_name,
                    NEW.partition_of_table_name
                )
            );
        ELSE
            IF NEW.active AND NOT OLD.active
            THEN
                action_stmt = format(
                    'ALTER TABLE %I.%I ATTACH PARTITION %I.%I ',
                    OLD.schema_name,
                    NEW.partition_of_table_name,
                    OLD.schema_name,
                    NEW.table_name
                );
                message_text = format(
                    'ATTACH PARITITION %I.%I TO %I.%I ',
                    OLD.schema_name,
                    NEW.table_name,
                    OLD.schema_name,
                    NEW.partition_of_table_name
                );
                IF ( (NEW.partition_parameters->>'default') = 'true' )
                THEN
                    action_stmts = array_append(
                        action_stmts,
                        action_stmt || 'DEFAULT ;'
                    );
                    messages = array_append(
                        messages,
                        message_text || 'AS DEFAULT PARITION'
                    );
                ELSE
                    EXECUTE format(
                        '
select format_type(
    (
        select atttypid
          from pg_attribute
         where attrelid = %L::regclass
           and attname = %L
    ),
    null
);
',
                        quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.partition_of_table_name),
                        quote_ident(NEW.partition_col)
                    )
                    INTO col_type_name;
                    action_stmt_2 = format(
                        'FOR VALUES FROM ( %L::%I ) TO ( %L::%I )',
                        NEW.partition_parameters->>'from',
                        col_type_name,
                        NEW.partition_parameters->>'to',
                        col_type_name
                    );
                    action_stmts = array_append(action_stmts, action_stmt || action_stmt_2);
                    messages = array_append(messages, message_text || action_stmt_2);
                END IF;
            END IF;
        END IF;
    ELSIF ( TG_OP = 'INSERT' )
    THEN
        action_stmt = format(
            'CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %I.%I ',
            NEW.schema_name,
            NEW.table_name,
            NEW.schema_name,
            NEW.partition_of_table_name
        );
        message_text = format(
            'CREATING NEW PARTITION %I.%I FOR %I.%I ',
            NEW.schema_name,
            NEW.table_name,
            NEW.schema_name,
            NEW.partition_of_table_name
        );
        IF ( (NEW.partition_parameters->>'default')::boolean )
        THEN
            action_stmts = array_append(
                action_stmts,
                action_stmt || 'DEFAULT ;'
            );
            messages = array_append(
                messages,
                message_text || 'AS DEFAULT PARITION'
            );
        ELSE
            EXECUTE format(
                        '
select format_type(
    (
        select atttypid
          from pg_attribute
         where attrelid = %L::regclass
           and attname = %L
    ),
    null
);
',
                quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.partition_of_table_name),
                quote_ident(NEW.partition_col)
            )
            INTO col_type_name;
            action_stmt_2 = format(
                'FOR VALUES FROM ( %L::%I ) TO ( %L::%I )',
                NEW.partition_parameters->>'from',
                col_type_name,
                NEW.partition_parameters->>'to',
                col_type_name
            );
            action_stmts = array_append(action_stmts, action_stmt || action_stmt_2);
            messages = array_append(messages, message_text || action_stmt_2);
        END IF;
    ELSE
        RAISE EXCEPTION 'Unhandled trigger operation %', TG_OP;
    END IF;

    /* Execute the action statements we've queued */
    total_actions = cardinality(action_stmts);
    LOOP
        EXIT WHEN action_ix > total_actions;

        RAISE INFO '%', messages[action_ix];
        EXECUTE action_stmts[action_ix];

        action_ix = action_ix + 1;
    END LOOP;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
