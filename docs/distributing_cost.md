# Distributing Cost
Our cost model allows user to distribute the their costs bassed of the cpu or memory usage of their user projects.

## Worker Unallocated Costs:

### How We Calculate

During data processing we add in additional rows to represent the [worker unallocated](https://github.com/project-koku/koku/blob/main/koku/masu/database/trino_sql/reporting_ocpusagelineitem_daily_summary.sql#L503) cost. These rows are added under the project name `Worker unallocated` during the ocp daily summary table creation. Formula:
```
unallocated_worker_cost = capacity - effective usage
```
The effective usage is the max(request, usage), since users can have a higer usage than their request.

### How We Distribute

One of the features of our cost models is to distribute the cost associated with the `Worker unallocated` project to the user projects with this algorithm:
```
distributed_cost = (user_project_usage / usage_of_all_user_projects) * worker_unallocated_cost
```

So, in this example lets say our worker unallocated cost equals 100 dollars. We have two user projects A & B. A has a usage of 25, and B has a usage of 75. Plugging into the algorithm above to distribute the worker unallocated cost we would do:

```
worker_unallocated_cost = 100
Project's A distributed_cost = (25 / sum(25 + 75)) * 100 = 25
Project's B distributed_cost = (75 / sum(25 + 75)) * 100 = 75
```

So, project A gets an additional 25 dollars, and Project B gets an additional 75 dollars added on due to distributing the Worker unallocated cost.

**How we deduplicate**
However, the `Worker unallocated` project that we created earlier in the *How We Calculate* section still holds the original cost, using the example above this would be our original 100 dollars. Therefore, in order to deduplicate costs for the `Worker unallocated` project we need to do:

```
distributed_cost = 0 - worker_uanllocated_cost
```

Working with our same example:

```

Worker unallocated project's distributed_cost = 0 - 100
```
