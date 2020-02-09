SELECT id, schema_name FROM public.api_tenant WHERE schema_name LIKE 'acct%';

DROP FUNCTION IF EXISTS tenant_schema_rename();

CREATE FUNCTION tenant_schema_rename() RETURNS integer AS $$
DECLARE
    r RECORD;
    orig_name text;
    new_name text;

BEGIN
    RAISE NOTICE 'Starting tenant schema rename...';

    FOR r IN SELECT id, schema_name FROM public.api_tenant WHERE schema_name LIKE 'acct%' LOOP
        orig_name = r.schema_name;
        new_name = split_part(r.schema_name, 'org', 1);
        RAISE NOTICE 'Current api_tenant schema_name %', orig_name;
        RAISE NOTICE 'New api_tenant schema_name %', new_name;
        UPDATE public.api_tenant SET schema_name=new_name WHERE id=r.id;
    END LOOP;


    RAISE NOTICE 'Done with tenant schema rename.';
    RETURN 1;
END;
$$ LANGUAGE plpgsql;

SELECT tenant_schema_rename();

SELECT id, schema_name FROM public.api_tenant WHERE schema_name LIKE 'acct%';
