--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
create or replace function public.tr_presto_delete_wrapper_log_action() returns trigger as $$
begin
    if NEW.result_rows is null
    then
        execute 'delete from ' || quote_ident(TG_TABLE_SCHEMA) || '.' || quote_ident(NEW.table_name) || ' ' ||
                NEW.where_clause;
        get diagnostics NEW.result_rows = row_count;
    end if;

    return NEW;
end;
$$ language plpgsql;
