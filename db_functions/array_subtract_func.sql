/*
Copyright 2021 Red Hat, Inc.

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
create or replace function public.array_subtract(
    minuend anyarray, subtrahend anyarray, out difference anyarray
)
returns anyarray as
$$
begin
    execute 'select array(select unnest($1) except select unnest($2))'
      using minuend, subtrahend
       into difference;
end;
$$ language plpgsql returns null on null input;
