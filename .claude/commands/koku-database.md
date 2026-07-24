---
description: "Run read-only SQL queries against prod/stage koku databases via gabi-cli"
---

Investigate the koku database. The argument is: $ARGUMENTS

The input can be:
- A SQL query to run
- A table or schema to explore
- A provider UUID, org_id, or customer to look up
- A question like "how many rows in rates_to_usage for org X?"

## Tool: gabi-cli

Use [gabi-cli](https://github.com/vkrizan/gabi-cli) for all database queries.
Install: `go install github.com/vkrizan/gabi-cli@latest`

`oc` must be logged in to the target cluster. Verify:

```bash
oc whoami 2>&1 && oc project 2>&1
```

If not logged in, tell the user to run `! oc login` with a token from the
OpenShift console (username → **Copy login command**).

| Env | Namespace | Console |
|-----|-----------|---------|
| **Prod** | `hccm-prod` | `https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com` |
| **Stage** | `hccm-stage` | `https://console-openshift-console.apps.crcs02ue1.urby.p1.openshiftapps.com` |

## Running queries

```bash
gabi-cli -n hccm-prod "SELECT current_timestamp;"   # one-shot
gabi-cli -n hccm-stage                               # interactive
```

Flags: `-q` (quiet), `-display table|expanded|auto`, `-fancy`.
**Queries must end with `;`** or they will not execute.

For multi-line queries:

```bash
QUERY=$(cat <<'EOF'
SELECT p.uuid, p.name, p.type, c.org_id
FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE p.uuid = 'YOUR-UUID';
EOF
)
gabi-cli -n hccm-prod -q "$QUERY"
```

## Schema structure

Koku uses django-tenants with PostgreSQL schemas:

- **`public`** — shared: `api_customer`, `api_provider`, `api_sources`
- **`orgNNNNNNN`** — per-tenant: `reporting_*`, `rates_to_usage`, `cost_model`, `cost_model_rate`

To query a tenant table: `SELECT * FROM orgNNNNNNN.rates_to_usage;`

### Finding the schema for a customer

```sql
SELECT schema_name FROM public.api_customer WHERE org_id = 'YOUR_ORG_ID';

SELECT c.schema_name, c.org_id FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE p.uuid = 'YOUR-UUID';
```

## Common queries

```sql
-- Providers for an org
SELECT p.uuid, p.name, p.type, p.setup_complete, p.active
FROM public.api_provider p
JOIN public.api_customer c ON p.customer_id = c.id
WHERE c.org_id = 'YOUR_ORG_ID';

-- Cost models for a tenant
SELECT uuid, name, source_type, updated_timestamp
FROM orgNNNNNNN.cost_model;

-- rates_to_usage row count
SELECT count(*) FROM orgNNNNNNN.rates_to_usage;

-- Recent manifests for a provider
SELECT id, billing_period_start_datetime, completed_datetime, num_total_files
FROM public.reporting_common_costusagereportmanifest
WHERE provider_id = 'YOUR-UUID'
ORDER BY id DESC LIMIT 10;
```

## Safety

- Queries run through GABI, which is deployed with a **read-only** PostgreSQL role — cannot modify data
- Queries timeout after ~60s
