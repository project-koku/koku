SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'acct%'

DROP FUNCTION IF EXISTS schema_rename();

CREATE FUNCTION schema_rename() RETURNS integer AS $$
DECLARE
    r RECORD;
    orig_name text;
    new_name text;

BEGIN
    RAISE NOTICE 'Starting schema rename...';

    FOR r IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'acct%' LOOP
        orig_name = r.schema_name;
        new_name = split_part(r.schema_name, 'org', 1);
        RAISE NOTICE 'Current schema_name %', orig_name;
        RAISE NOTICE 'New schema_name %', new_name;
        EXECUTE 'ALTER SCHEMA ' || orig_name || ' RENAME TO ' || new_name ;
    END LOOP;

    RAISE NOTICE 'Done with schema rename.';
    RETURN 1;
END;
$$ LANGUAGE plpgsql;

SELECT schema_rename();

SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'acct%'
