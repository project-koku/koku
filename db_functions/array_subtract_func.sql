--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
CREATE OR REPLACE FUNCTION public.array_subtract(
    minuend anyarray, subtrahend anyarray, OUT difference anyarray
)
RETURNS anyarray AS
$$
begin
    execute 'select array(select unnest($1) except select unnest($2))'
      using minuend, subtrahend
       into difference;
end;
$$ LANGUAGE plpgsql RETURNS NULL ON NULL INPUT
;
