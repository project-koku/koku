--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
CREATE OR REPLACE FUNCTION public.tr_presto_delete_wrapper_log_action() RETURNS trigger AS $$
begin
    if NEW.result_rows is null
    then
        execute 'delete from ' || quote_ident(TG_TABLE_SCHEMA) || '.' || quote_ident(NEW.table_name) || ' ' ||
                NEW.where_clause;
        get diagnostics NEW.result_rows = row_count;
    end if;

    return NEW;
end;
$$ LANGUAGE plpgsql;
