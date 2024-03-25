These filters were added to reduce unnecessary rows from being added to the ocp daily summary tables during insert call:
```
AND node_capacity_cpu_core_hours IS NOT NULL
AND node_capacity_cpu_core_hours != 0
AND cluster_capacity_cpu_core_hours IS NOT NULL
AND cluster_capacity_cpu_core_hours != 0
```

However, these rows are causing the `Worker unallocated` namespace to be removed during the insert so that cost is not being negated properly. The changes I have made in the SQL are to move the select for that insert into a separate common table expression so that we can better control unnecessary rows from being inserted into the table.

1. Check out main and load customer data for onprem and aws. Check for unnecessary rows:

Worker unallocated:
```
select count(*) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'worker_distributed' and (distributed_cost = 0 or distributed_cost is null);
```

Result:
```
 count
-------
   300
(1 row)
```

Platform:
```
select count(*) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'platform_distributed' and (distributed_cost = 0 or distributed_cost is null);
```
Result:
```
 count
-------
   900
(1 row)
```

You will notice that the `Platform` cost has more unnecessary rows that the `Worker unallocated` project but not none? Why? If we look at the sources:

Platform
```
select distinct(source_uuid) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'platform_distributed' and (distributed_cost = 0 or distributed_cost is null);
```
Result:
```
             source_uuid
--------------------------------------
 bc021726-e47e-42b6-b9ad-aaf1ebd140ee
 aa8543c3-335c-4a4c-b4b9-c3726ef15140
```

Worker unallocated:
```
select distinct(source_uuid) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'worker_distributed' and (distributed_cost = 0 or distributed_cost is null);
```
Result:
```
             source_uuid
--------------------------------------
 bc021726-e47e-42b6-b9ad-aaf1ebd140ee
```

The filters mentioned above are what is keeping the bloat to be less on the worker unallocated project. We had to [remove these filters](https://github.com/project-koku/koku/pull/4404/files#diff-e4f96a7457f5a8b243e960d406eb66f28c91d60885bbacbf954dd574f0d63959L148-L152) in order for volume cost to be distributed correctly. Which is why the problem is worse on the `Platform` project.

However, our ultimate goal here is to return zero rows when the distributed_cost is zero.

2. Check out this branch & resummarize the sources.
3. After resummary, run the counts again and see they come back zero now.
4. Check the distributed cost.
```
postgres=# select sum(distributed_cost) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'worker_distributed';
        sum
--------------------
 -0.000000000000042
```
```
postgres=# select sum(distributed_cost) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type = 'platform_distributed';
        sum
--------------------
 -0.000000000000030
 ```
