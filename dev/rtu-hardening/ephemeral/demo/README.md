# RTU demo queries (ephemeral)

For a namespace set up with `deploy.sh` and `testdata.sh` (test org `7654321`, clusters `rtu-cluster-a` and `rtu-cluster-b`). `NS` is the namespace.

```bash
NS=ephemeral-xxxxxx
DB=$(oc --context eph -n $NS get pods -o name | grep '/koku-db-' | head -1)

# 1. The three layers per cluster and month: RTU rows and cost, daily summary cost model cost, breakdown tree
oc --context eph -n $NS exec -i "$DB" -- psql -d koku < dev/rtu-hardening/ephemeral/demo/layers.sql

# 2. What users see: the OCP costs report API (runs in the toolbox pod, x-rh-identity of the test org)
oc --context eph -n $NS exec -i rtu-toolbox -- python3 - < dev/rtu-hardening/ephemeral/demo/costs_api.py

# 3. Per rate: RTU against the breakdown leaves (cluster A, October)
oc --context eph -n $NS exec -i "$DB" -- psql -d koku < dev/rtu-hardening/ephemeral/demo/breakdown_gap.sql
```

`dev/rtu-hardening/ephemeral/testdata.sh verify` shows the tenant, the latest migration, the `rates_to_usage` constraints, RTU rows per source and month, and `rate_id` on distributed rows.

## Result (2026-11-28, `ephemeral-grnfft`, image `pr-6425-3468c5e`)

| | October | November (to the 28th) |
|---|---|---|
| RTU rows per cluster | 23,622 | 21,140 |
| RTU cost = daily summary cost = costs API total | 104,863.78 | 95,631.91 |
| Cost breakdown total (`total_cost` root), cluster A | 60,789.67 | 46,375.23 |

The cost breakdown does not add up to the cluster's cost. `reporting_ocp_cost_breakdown_p.sql` takes rows with a `monthly_cost_type` only for their positive `distributed_cost` (step 2), and excludes them from the project leaves (step 1, `monthly_cost_type IS NULL`). `monthly_cost_type` holds both distribution types (`platform_distributed`, ...) and real monthly costs (`Node`, `Cluster`, `PVC`, `OCP_VM`, `Tag`), so the own cost of every monthly rate never reaches the breakdown (cluster A, October: 76,238.07, of which the GPU monthly tag rate is 55,053.57), and neither do the negative rows distribution writes for the cost it moves. Same SQL on `main` (since #6163) and in #6102; RTU flag only.
