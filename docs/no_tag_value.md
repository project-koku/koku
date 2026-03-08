# The "No-\<tag\>" Catch-All Value

When you group a cost report by a tag key, the response includes one entry per distinct value of that tag. Resources that **don't have the tag at all** are grouped together under a synthetic value: `No-<tag key>`.

For example, `group_by[tag:environment]=*` will produce entries like `environment: production`, `environment: staging`, and `environment: No-environment` — the last one representing all resources that have no `environment` tag.

The same behavior applies to non-tag group dimensions (`project`, `node`, `region`, etc.) when a row has a `NULL` value for that column.

## Why It Exists

Tag coverage is rarely complete. A team might tag most of their EC2 instances with `env=prod` but leave a few untagged. Without a catch-all bucket, the cost for those untagged resources would silently disappear from the grouped report. `No-<tag>` ensures the total always reconciles — every dollar of cost is accounted for.

## How the Value Is Formed

The label is `No-` followed by the tag key as supplied in the request (without the `tag:` prefix):

| Query parameter | Catch-all label |
|---|---|
| `group_by[tag:environment]=*` | `No-environment` |
| `group_by[tag:app]=*` | `No-app` |
| `group_by[tag:cost-center]=*` | `No-cost-center` |
| `group_by[project]=*` | `No-project` |
| `group_by[region]=*` | `No-region` |

## Where It Is Applied

This happens in the API layer, in [`ReportQueryHandler._apply_group_null_label`](https://github.com/project-koku/koku/blob/main/koku/api/report/queries.py). After the database query returns, any row where the grouped column is `NULL` or an empty string gets its value replaced with `No-<group>` before the response is assembled.

The database itself stores `NULL` — the `No-<tag>` string is never written to any table.

## Filtering and Excluding

`No-<tag>` behaves like any other tag value for the purposes of filtering:

```
# only show untagged resources
GET /api/cost-management/v1/reports/aws/costs/?group_by[tag:environment]=*&filter[tag:environment]=No-environment

# exclude untagged resources from the report
GET /api/cost-management/v1/reports/aws/costs/?group_by[tag:environment]=*&exclude[tag:environment]=No-environment
```

Note: When you exclude specific tag values, `No-<tag>` will still appear in the response as long as there are untagged resources — it is not automatically excluded.

## Ordering

When sorting by a tag column, `No-<tag>` rows sort as if their value is the literal string `No-<tag key>`. There is no special placement; the sort is alphabetical unless you specify a direction.

## Example Response

```json
{
  "data": [
    {
      "date": "2026-03",
      "environments": [
        {
          "environment": "production",
          "values": [{ "cost": { "total": { "value": 1200.00, "units": "USD" } } }]
        },
        {
          "environment": "staging",
          "values": [{ "cost": { "total": { "value": 340.00, "units": "USD" } } }]
        },
        {
          "environment": "No-environment",
          "values": [{ "cost": { "total": { "value": 85.50, "units": "USD" } } }]
        }
      ]
    }
  ]
}
```

The `No-environment` entry here represents resources that had no `environment` tag during that billing period.
