--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

create or replace function public.jsonb_sha256_text(j_param jsonb, out hash_val text)
returns text
as $$
begin
    select encode(sha256(decode(string_agg(key || ':' || value, '|'), 'escape')), 'hex')
      from (
             select *
               from jsonb_each_text(j_param)
              order by key, value
           ) as ordered_jsonb
      into hash_val;
end;
$$ language plpgsql returns null on null input
immutable
;
