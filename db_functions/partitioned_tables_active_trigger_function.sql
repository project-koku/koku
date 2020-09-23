

DROP FUNCTION IF EXISTS public.trfn_attach_date_range_partition();
CREATE OR REPLACE FUNCTION public.trfn_attach_date_range_partition() RETURNS TRIGGER AS $$
DECLARE
    alter_stmt text = '';
    msg text = '';
BEGIN
    IF NEW.active != OLD.active
    THEN
        IF NEW.active = false
        THEN
            alter_stmt = 'ALTER TABLE ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name) ||
                        ' DETACH PARTITION ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name)
                        || ' ;';
            msg = 'DETACH PARTITION ' ||
                quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name);
        ELSE
            alter_stmt = 'ALTER TABLE ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.partition_of_table_name) ||
                        ' ATTACH PARTITION ' ||
                        quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name) || ' ';
            IF ( (NEW.partition_parameters->>'default')::boolean )
            THEN
                alter_stmt = alter_stmt || 'DEFAULT ;';
                msg = 'DEFAULT';
            ELSE
                alter_stmt = alter_stmt || 'FOR VALUES FROM ( ' ||
                                quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                                quote_literal(NEW.partition_parameters->>'to') || '::date ) ;';
                msg = 'FOR VALUES FROM ( ' ||
                    quote_literal(NEW.partition_parameters->>'from') || '::date ) TO (' ||
                    quote_literal(NEW.partition_parameters->>'to') || '::date )';
            END IF;
            msg = 'ATTACH PARTITION ' ||
                quote_ident(OLD.schema_name) || '.' || quote_ident(OLD.table_name) ||
                ' ' || msg;
        END IF;

        RAISE NOTICE 'ALTER TABLE %.% : %',
                     quote_ident(NEW.schema_name), quote_ident(NEW.partition_of_table_name), msg;
        EXECUTE alter_stmt;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
