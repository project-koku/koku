# Distributing Cost
Our cost model allows user to distribute the their costs bassed of the CPU or memory usage of their user projects.

## Worker Unallocated Costs:

### How We Calculate

During data processing we add in additional rows to represent the [worker unallocated](https://github.com/project-koku/koku/blob/main/koku/masu/database/trino_sql/openshift/reporting_ocpusagelineitem_daily_summary.sql) cost. These rows are added under the project name `Worker unallocated` during the OCP daily summary table creation. Formula:
```
unallocated_worker_cost = capacity - effective usage
```
The effective usage is the `max(request, usage)`, since users can have a higer usage than their request.

### How We Distribute

One of the features of our cost models is to distribute the cost associated with the `Worker unallocated` project to the user projects with this algorithm:
```
distributed_cost = (user_project_usage / usage_of_all_user_projects) * worker_unallocated_cost
```

For example, there are worker unallocated cost of 100 dollars and two user projects, A and B. Project A has a usage of 25 and project B has a usage of 75. Using the algorithm above to distribute the worker unallocated cost:

```
worker_unallocated_cost = 100
Project's A distributed_cost = (25 / sum(25 + 75)) * 100 = 25
Project's B distributed_cost = (75 / sum(25 + 75)) * 100 = 75
```

Project A gets an additional 25 dollars and Project B gets an additional 75 dollars due to distributing the worker unallocated cost.

**How we deduplicate**

The `Worker unallocated` project that we created earlier in the *How We Calculate* section still holds the original cost. Using the example above this would be our original 100 dollars. In order to deduplicate costs for the `Worker unallocated` project we need to subtract the unallocated costs:

```
distributed_cost = 0 - worker_uanllocated_cost
```

Working with our same example:

```
Worker unallocated project's distributed_cost = 0 - 100
```
