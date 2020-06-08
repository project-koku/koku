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
-- Function to generate a sha256 hash from the concatenation
-- of all of the text values passed into the function
create or replace function public.record_hash ( VARIADIC vals text[] ) returns text as
$$
declare
    record_val text = '';
    i int = 1;
begin
    for i in 1 .. array_upper(vals, 1)
    loop
        if vals[i] is null
        then
            vals[i] = '';
        end if;
        record_val = record_val || vals[i];
    end loop;

    if record_val = ''
    then
        record_val = null::text;
    else
        select encode(sha256(decode(record_val, 'escape')), 'hex') into record_val;
    end if;

    return record_val;
end;
$$
language plpgsql
returns null on null input;
