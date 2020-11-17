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
