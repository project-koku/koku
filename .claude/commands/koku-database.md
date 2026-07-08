---
description: "Run read-only SQL queries against prod/stage koku databases via gabi-cli"
---

Investigate the koku database. The argument is: $ARGUMENTS

The input can be:
- A SQL query to run
- A table or schema to explore
- A provider UUID, org_id, or customer to look up
- A question like "how many rows in rates_to_usage for org X?"

## Prerequisites

**gabi-cli** must be installed (`go install github.com/vkrizan/gabi-cli@latest`)
and on `$PATH`. `oc` must be logged in to the target cluster.

### Verify access

```bash
# Check if oc is logged in and which cluster/namespace
oc whoami 2>&1 && oc project 2>&1
```

If not logged in, tell the user:

> Run `! oc login --token=TOKEN --server=<CLUSTER_URL>` then `kubens <NAMESPACE>`.
> Get the token: open the console link below, click your username (top right) → **Copy login command** → copy the `--token=` value.
>
> - **Prod console:** https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com
> - **Stage console:** https://console-openshift-console.apps.crcs02ue1.urby.p1.openshiftapps.com

### Cluster/namespace reference

| Env | Cluster URL | Namespace | Gabi route |
|-----|------------|-----------|------------|
| **Prod** | `https://api.crcp01ue1.o9m8.p1.openshiftapps.com:6443` | `hccm-prod` | `https://gabi-cost-management-prod.apps.crcp01ue1.o9m8.p1.openshiftapps.com` |
| **Stage** | `https://api.crcs02ue1.urby.p1.openshiftapps.com:6443` | `hccm-stage` | `https://gabi-cost-management-stage.apps.crcs02ue1.urby.p1.openshiftapps.com` |

## Running queries

### Interactive mode

```bash
gabi-cli                     # uses current oc context
gabi-cli -n hccm-prod        # explicit namespace
gabi-cli -n hccm-stage       # stage
```

Drops into an interactive SQL prompt (`gabi>`). Type queries, end with `;`.

### One-shot mode

```bash
gabi-cli "SELECT current_timestamp;"
gabi-cli -n hccm-prod "SELECT count(*) FROM public.api_customer;"
```

Pass the SQL as a positional argument. **Queries must end with `;`** or they will not execute.

Flags:
- `-n NAMESPACE` — target namespace
- `-q` — suppress logging messages (cleaner output for scripting)
- `-display table|expanded|auto` — output format (default: auto)
- `-fancy` — rounded table style with colored header

### Multi-line queries from a variable

```bash
QUERY=$(cat <<'EOF'
SELECT p.uuid, p.name, p.type, p.setup_complete, c.org_id
FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE p.uuid = 'YOUR-UUID';
EOF
)
gabi-cli -n hccm-prod -q "$QUERY"
```

## Schema structure

Koku uses django-tenants with PostgreSQL schemas:

- **`public` schema** — shared tables: `api_customer`, `api_provider`, `api_user`, `api_sources`, `django_tenants_tenant`
- **`orgNNNNNNN` schemas** — per-tenant tables: `reporting_*`, `rates_to_usage`, `cost_model`, `cost_model_rate`, `price_list`

To query a tenant table, prefix with the schema: `orgNNNNNNN.rates_to_usage`.

### Finding the schema for a customer

```sql
-- By org_id
SELECT schema_name FROM public.api_customer WHERE org_id = 'YOUR_ORG_ID';

-- By provider UUID
SELECT c.schema_name, c.org_id FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE p.uuid = 'YOUR-UUID';
```

## Common queries

### Customer & provider lookup

```sql
-- Recent customers
SELECT id, uuid, org_id, account_id, schema_name, date_created
FROM public.api_customer ORDER BY date_created DESC LIMIT 10;

-- Providers for an org
SELECT p.uuid, p.name, p.type, p.setup_complete, p.active
FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE c.org_id = 'YOUR_ORG_ID';

-- Sources
SELECT source_id, name, source_type, provider_id, koku_uuid, status
FROM public.api_sources ORDER BY source_id DESC LIMIT 10;
```

### Cost model investigation

```sql
-- Cost models for a tenant
SELECT uuid, name, source_type, updated_timestamp
FROM org12345678.cost_model;

-- Rates for a cost model
SELECT uuid, metric, cost_type, default_rate, custom_name
FROM org12345678.cost_model_rate
WHERE price_list_id IN (
    SELECT price_list_id FROM org12345678.price_list_cost_model_map
    WHERE cost_model_id = 'COST-MODEL-UUID'
);

-- rates_to_usage row counts for a tenant
SELECT count(*) FROM org12345678.rates_to_usage;

-- FK constraint check on rates_to_usage (are constraints present on all partitions?)
SELECT c.conrelid::regclass AS "table",
       c.conname AS "constraint",
       c.condeferrable AS "deferrable",
       c.condeferred AS "deferred",
       c.confdeltype AS "delete_action"
FROM pg_constraint c
WHERE c.conrelid IN (
    SELECT inhrelid FROM pg_inherits
    WHERE inhparent = 'org12345678.rates_to_usage'::regclass
    UNION ALL
    SELECT 'org12345678.rates_to_usage'::regclass
)
AND c.contype = 'f'
ORDER BY c.conrelid::regclass::text;
```

### Cross-tenant queries (advanced)

Generate a UNION ALL query across all tenant schemas:

```sql
SELECT string_agg(
    format('SELECT count(*) AS row_count FROM %I.rates_to_usage', nsp.nspname),
    ' UNION ALL '
)
FROM pg_catalog.pg_class cls
JOIN pg_catalog.pg_namespace nsp ON nsp.oid = cls.relnamespace
WHERE cls.relname = 'rates_to_usage'
  AND nsp.nspname LIKE 'org%';
```

This produces a giant UNION ALL query. Copy-paste the output as a subquery:

```sql
SELECT row_count, count(*) AS num_tenants
FROM (
    <paste the generated UNION ALL here>
) t
GROUP BY row_count
ORDER BY row_count;
```

### Manifest / processing status

```sql
-- Recent manifests for a provider
SELECT id, provider_id, billing_period_start_datetime, manifest_completed_datetime, status
FROM public.reporting_common_costusagereportmanifest
WHERE provider_uuid = 'YOUR-UUID'
ORDER BY id DESC LIMIT 10;
```

## Fallback: curl (if gabi-cli doesn't work)

Requires a manually extracted token from the OpenShift console.

```bash
OC_TOKEN="$(oc whoami -t)"
curl -s -H "Authorization: Bearer $OC_TOKEN" \
  -d '{"query": "SELECT current_timestamp;"}' \
  https://gabi-cost-management-prod.apps.crcp01ue1.o9m8.p1.openshiftapps.com/query | jq
```

## Safety

- gabi is **read-only** — all queries run through a restricted PostgreSQL role that cannot modify data
- Queries that take too long will be killed by the server (timeout ~60s)
- Build and test complex queries against local PostgreSQL first
