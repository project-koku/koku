--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
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
$$ language plpgsql returns null on null input
;
