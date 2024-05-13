

1. Load test customer data
```
make load-test-customer-data test_source=Azure
```
2. Create a `Unattributed Storage` project
The distribution for storage unattributed is based off of the name of the namespace. We can convert an existing namespace over to this project for the purposes of testing if the distribution algorithm is working correctly.

- `PGPASSWORD=postgres psql postgres -U postgres -h localhost -p 15432`
- `set search_path=org1234567;`
**Pick out a namespace:**
```
postgres=# SELECT DISTINCT namespace FROM reporting_ocpusagelineitem_daily_summary where usage_start > '2024-05-01' and infrastructure_raw_cost IS NOT NULL and cluster_id='my-ocp-cluster-2';
        namespace
--------------------------
 Platform unallocated
 Worker unallocated
 openshift
 openshift-kube-apiserver
 kube-system
 news-site
 mobile
 banking
```
Switch all of the infrastructure raw cost related to one of these namespaces to the `Storage unattributed` project:
```
UPDATE reporting_ocpusagelineitem_daily_summary set namespace = 'Storage unattributed' where namespace='mobile' and infrastructure_raw_cost IS NOT NULL;
```

3. Note the infrastructure cost of the now `Storage unattributed` project.
```
select sum(infrastructure_raw_cost) from reporting_ocpusagelineitem_daily_summary where namespace = 'Storage unattributed' and usage_start >= '2024-05-01';
```
```
        sum
-------------------
 5.155869243000000
(1 row)
```
4. Create a cost model for the openshift source that has been correlated with the Azure source.

The cost model will be applied to the current data in the daily summary table.

`http://localhost:8000/api/cost-management/v1/sources/?type=OCP`

Find the uuid for the `Test OCP on Azure` source.

Send a post to:
```
http://127.0.0.1:8000/api/cost-management/v1/cost-models/
```

Body:
```
{
  "name": "Cost Management OpenShift Cost Model",
  "description": "A cost model of on-premises OpenShift clusters.",
  "source_type": "OCP",
  "source_uuids": [
    "901d1eda-a16e-4bc1-8e46-48ce1e657976"
  ],
  "rates": [
    {
      "metric": {
        "name": "node_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Currency",
        "label_measurement_unit": "node-month"
      },
      "description": "",
      "tag_rates": {
        "tag_key": "app",
        "tag_values": [
          {
            "unit": "USD",
            "usage": {
              "unit": "USD",
              "usage_end": null,
              "usage_start": null
            },
            "value": 24000,
            "default": true,
            "tag_value": "smoking",
            "description": ""
          },
          {
            "unit": "USD",
            "usage": {
              "unit": "USD",
              "usage_end": null,
              "usage_start": null
            },
            "value": 250,
            "default": false,
            "tag_value": "bigsmoke",
            "description": ""
          }
        ]
      },
      "cost_type": "Supplementary"
    },
    {
      "metric": {
        "name": "node_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Currency",
        "label_measurement_unit": "node-month"
      },
      "description": "",
      "tag_rates": {
        "tag_key": "app",
        "tag_values": [
          {
            "unit": "USD",
            "usage": {
              "unit": "USD",
              "usage_end": null,
              "usage_start": null
            },
            "value": 123,
            "default": true,
            "tag_value": "smoke",
            "description": ""
          }
        ]
      },
      "cost_type": "Infrastructure"
    },
    {
      "metric": {
        "name": "node_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Currency",
        "label_measurement_unit": "node-month"
      },
      "description": "",
      "tag_rates": {
        "tag_key": "web",
        "tag_values": [
          {
            "unit": "USD",
            "usage": {
              "unit": "USD",
              "usage_end": null,
              "usage_start": null
            },
            "value": 456,
            "default": true,
            "tag_value": "smoker",
            "description": ""
          }
        ]
      },
      "cost_type": "Infrastructure"
    },
    {
      "metric": {
        "name": "cluster_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Currency",
        "label_measurement_unit": "node-month"
      },
      "description": "",
      "tag_rates": {
        "tag_key": "app",
        "tag_values": [
          {
            "unit": "USD",
            "usage": {
              "unit": "USD",
              "usage_end": null,
              "usage_start": null
            },
            "value": 456,
            "default": true,
            "tag_value": "smoker",
            "description": ""
          }
        ]
      },
      "cost_type": "Infrastructure"
    }
  ],
  "distribution": "memory",
  "distribution_info": {
      "distribution_type": "memory",
      "platform_cost": true,
      "worker_cost": true,
      "storage_unattributed": true
  }
}
```

5. Verification SQL:

**Check the total sum:**
```
postgres=# select sum(distributed_cost) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type='unattributed_storage';
        sum
--------------------
 -0.000000000000002
(1 row)
```
This should be very close to 0, we negate the cost we distribute as we go. So the combined cost should be zero.

**Check the negated cost:**
```
select sum(distributed_cost) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type='unattributed_storage' and namespace = 'Storage unattributed';
```
This will match the cost
```
        sum
--------------------
 -5.155869243000000
```

**Check the distributed cost:**
```
select sum(distributed_cost) from reporting_ocpusagelineitem_daily_summary where cost_model_rate_type='unattributed_storage' and namespace != 'Storage unattributed';
```
```
        sum
-------------------
 5.155869242999997
```
