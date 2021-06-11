--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

DROP FUNCTION IF EXISTS public.trfn_manage_date_range_partition();
CREATE OR REPLACE FUNCTION public.trfn_manage_date_range_partition() RETURNS TRIGGER AS $$
DECLARE
    alter_stmt text = '';
    action_stmt text = '';
    alter_msg text = '';
    action_msg text = '';
    table_name text = '';
BEGIN
    IF ( TG_OP = 'DELETE' )
    THEN
        IF ( OLD.active )
        THEN
            alter_stmt = 'ALTER TABLE ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name) ||
                        ' DETACH PARTITION ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name) ||
                        ' ;';
        END IF;
        action_stmt = 'DROP TABLE IF EXISTS ' || quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name) || ' ;';
        table_name = quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name);
        alter_msg = 'DROP PARTITION ' || quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name);
    ELSIF ( TG_OP = 'UPDATE' )
    THEN
        /* If the partition was active, then detach it */
        if ( OLD.active )
        THEN
            alter_stmt = 'ALTER TABLE ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name) ||
                        ' DETACH PARTITION ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name)
                        || ' ;';
        END IF;

        /* If we are going to active or are still active, then attach the partition */
        if ( NEW.active )
        THEN
            action_stmt = 'ALTER TABLE ' ||
                            quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name) ||
                            ' ATTACH PARTITION ' ||
                            quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name) || ' ';
            IF ( (NEW.partition_parameters->>'default') = 'true' )
            THEN
                action_stmt = action_stmt || 'DEFAULT ;';
                action_msg = 'DEFAULT';
            ELSE
                action_stmt = action_stmt || 'FOR VALUES FROM ( ' ||
                            quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                            quote_literal(NEW.partition_parameters->>'to') || '::date ) ;';
                action_msg = 'FOR VALUES FROM ( ' ||
                            quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                            quote_literal(NEW.partition_parameters->>'to') || '::date )';
            END IF;
        END IF;

        table_name = quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.partition_of_table_name);
        action_msg = 'ALTER PARTITION ' || quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.table_name) ||
                     ' ' || action_msg;
    ELSIF ( TG_OP = 'INSERT' )
    THEN
        action_stmt = 'CREATE TABLE IF NOT EXISTS ' ||
                      quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.table_name) || ' ' ||
                      'PARTITION OF ' ||
                      quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.partition_of_table_name) || ' ';
        IF ( (NEW.partition_parameters->>'default')::boolean )
        THEN
            action_stmt = action_stmt || 'DEFAULT ;';
            action_msg = 'DEFAULT';
        ELSE
            action_stmt = action_stmt || 'FOR VALUES FROM ( ' ||
                          quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                          quote_literal(NEW.partition_parameters->>'to') || '::date ) ;';
            action_msg = 'FOR VALUES FROM ( ' ||
                         quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                         quote_literal(NEW.partition_parameters->>'to') || '::date )';
        END IF;
        action_msg = 'CREATE PARTITION ' || quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.table_name) ||
                     ' ' || action_msg;
        table_name = quote_ident(NEW.schema_name) || '.' || quote_ident(NEW.partition_of_table_name);
    ELSE
        RAISE EXCEPTION 'Unhandled trigger operation %', TG_OP;
    END IF;

    IF ( alter_stmt != '' )
    THEN
        IF ( alter_msg != '' )
        THEN
            RAISE NOTICE 'ALTER TABLE % : %', table_name, alter_msg;
        END IF;

        EXECUTE alter_stmt;
    END IF;

    IF ( action_stmt != '' )
    THEN
        IF ( action_msg != '' )
        THEN
            RAISE NOTICE 'ALTER TABLE % : %', table_name, action_msg;
        END IF;

        EXECUTE action_stmt;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
