--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--
-- ===================================================
-- setup normal tables that will be truncated, dropped after this processing.
-- ===================================================

-- Make sure that the tables do not already exist
-- PostgreSQL has no TRUNCATE TABLE IF EXISTS form, so we have to do this.
do $$
declare
    processing_tables text[] := ARRAY['{{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}}',
                                      '{{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}}',
                                      '{{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}}']::text[];
    table_name text;
begin
    foreach table_name in array processing_tables
    loop
        if (to_regclass(table_name) is not NULL)
        then
            raise info 'Truncating table %%', table_name;
            execute format('truncate table %%s;', table_name);
            raise info 'Dropping table %%', table_name;
            execute format('drop table %%s;', table_name);
        end if;
    end loop;
end;
$$ language plpgsql;


create table {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} as
SELECT distinct
       key,
       value,
       li.report_period_id,
       li.namespace,
       li.node
  FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS li,
       jsonb_each_text(li.pod_labels) labels
 WHERE li.data_source = 'Storage'
{% if report_periods %}
   AND li.report_period_id IN (
    {%- for report_period_id in report_period_ids -%}
       {{report_period_id}}{% if not loop.last %},{% endif %}
    {%- endfor -%}
       )
{% endif %}
   AND li.usage_start >= {{start_date}}::date
   AND li.usage_start <= {{end_date}}::date
   AND value IS NOT NULL
;

create index ix_expanded_tag_values on {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} (key, report_period_id, namespace, node);


create table {{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}} as
select key,
       array_agg(distinct value) as "values",
       report_period_id,
       namespace,
       node
  from (
           select r.key,
                  r.value,
                  r.report_period_id,
                  r.namespace,
                  r.node
             from {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} as r
            union
           select e.key,
                  unnest(e."values") as "value",
                  e.report_period_id,
                  e.namespace,
                  e.node
             from {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary as e
             join {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} r1
               on r1.key = e.key
              and r1.report_period_id = e.report_period_id
              and r1.namespace = e.namespace
              and r1.node = e.node
       ) as x
 group
    by key,
       report_period_id,
       namespace,
       node
;

create index ix__expanded_tag_values_{{uuid | sqlsafe}} on {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} (key, report_period_id, namespace, node);


create table {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}} as
select uuid_generate_v4() as "uuid",
       tv.key,
       tv.value,
       array_agg(distinct rp.cluster_id) as cluster_ids,
       array_agg(distinct rp.cluster_alias) as cluster_aliases,
       array_agg(distinct tv.namespace) as namespaces,
       array_agg(distinct tv.node) as nodes
  from {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}} tv
  join {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
    on tv.report_period_id = rp.id
 group
    by tv.key,
       tv.value
;

create index ix__process_ocptagvalues_{{uuid | sqlsafe}} on {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}} (key, value);


-- ===================================================
-- Handle reporting_ocpstoragevolumelabel_summary
-- ===================================================
update {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary as pl_summ
   set "values" = pls."values"
  from {{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}} pls
 where pls.key = pl_summ.key
   and pls.report_period_id = pl_summ.report_period_id
   and pls.namespace = pl_summ.namespace
   and pls.node = pl_summ.node
;


insert
  into {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (
           "uuid",
           key,
           "values",
           report_period_id,
           namespace,
           node
       )
select uuid_generate_v4(),
       key,
       "values",
       report_period_id,
       namespace,
       node
  from {{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}} atvi
 where not exists (
                      select 1
                        from {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary ins
                       where atvi.key = ins.key
                         and atvi.report_period_id = ins.report_period_id
                         and atvi.namespace = ins.namespace
                         and atvi.node = ins.node
                  )
;


-- ===================================================
-- Handle reporting_ocptags_values
-- ===================================================
update {{schema | sqlsafe}}.reporting_ocptags_values as otv
   set cluster_ids = rp.cluster_ids,
       cluster_aliases = rp.cluster_aliases,
       namespaces = rp.namespaces,
       nodes = rp.nodes
  from {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}} rp
 where otv.key = rp.key
   and otv.value = rp.value
;


insert
  into {{schema | sqlsafe}}.reporting_ocptags_values
select uuid_generate_v4(),
       rp.key,
       rp.value,
       rp.cluster_ids,
       rp.cluster_aliases,
       rp.namespaces,
       rp.nodes
  from {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}} rp
 where not exists (
                      select 1
                        from {{schema | sqlsafe}}.reporting_ocptags_values otv
                       where otv.key = rp.key
                         and otv.value = rp.value
                  )
;


-- We run this SQL in the volume label summary SQL as it is run after
-- the pod summary SQL and we want to make sure we consider both
-- source tables before deleting from the values table.
DELETE FROM {{schema | sqlsafe}}.reporting_ocptags_values tv
 WHERE NOT EXISTS (
                      select 1
                        from {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS pls
                       where pls.key = tv.key
                  )
   AND NOT EXISTS (
                      select 1
                        from {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS pls
                       where pls.key = tv.key
                  )
;


-- Cleanup
truncate table {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}};
truncate table {{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}};
truncate table {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}};
drop table {{schema | sqlsafe}}._process_ocptagvalues_{{uuid | sqlsafe}};
drop table {{schema | sqlsafe}}._report_period_tag_values_{{uuid | sqlsafe}};
drop table {{schema | sqlsafe}}._expanded_tag_values_{{uuid | sqlsafe}};
