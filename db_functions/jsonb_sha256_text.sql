--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

CREATE OR REPLACE FUNCTION public . jsonb_sha256_text(j_param jsonb, OUT hash_val text)
RETURNS text
AS $$
begin
    select encode(sha256(decode(string_agg(key || ':' || value, '|'), 'escape')), 'hex')
      from (
             select *
               from jsonb_each_text(j_param)
              order by key, value
           ) as ordered_jsonb
      into hash_val;
end;
$$ LANGUAGE plpgsql RETURNS NULL ON NULL INPUT
IMMUTABLE
;
