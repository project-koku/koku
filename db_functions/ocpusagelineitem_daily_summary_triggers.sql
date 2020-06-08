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
-- Trigger function to dynamically set the record_hash for the primary key value
-- This trigger function should only be applied to BEFORE INSERT OR BEFORE UPDATE
-- on the reporting_ocpusagelineitem_daily_summary partitioned table.
create or replace function pre_trg_ocpusagelineitemdailysummary_pk() returns trigger as
$$
begin
    if TG_OP in ('INSERT', 'UPDATE')
    then
        NEW.id = public.record_hash(NEW.usage_start::text,
                                    NEW.cluster_id::text,
                                    NEW.namespace::text,
                                    NEW.node::text,
                                    NEW.pod_labels::text);
        return NEW;
    else
        return null;
    end if;
end;
$$
language plpgsql;


create trigger pre_ins_ocpusagelineitemdailysummary_pk
before insert
    on reporting_ocpusagelineitem_daily_summary
   for each row execute function pre_trg_ocpusagelineitemdailysummary_pk()
   not deferrable;


create trigger pre_udt_ocpusagelineitemdailysummary_pk
before update
    of usage_start, cluster_id, namespace, node, pod_labels
    on reporting_ocpusagelineitem_daily_summary
   for each row execute function pre_trg_ocpusagelineitemdailysummary_pk()
   not deferrable;
