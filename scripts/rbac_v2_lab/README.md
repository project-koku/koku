# RBAC v2 lab

Reproduces the experimental `RBAC_BACKEND=v2` path: koku reads RBAC v2 role
bindings (instead of `/api/rbac/v1/access/`), keeps permission evaluation local,
and maps workspaces to the concrete resource ids it already scopes reports by.

## Prerequisites

1. A Kessel development stack with RBAC v2 and Inventory:

   ```bash
   git clone https://github.com/project-kessel/inventory-api.git
   cd inventory-api
   make kessel-up      # RBAC on :9080, Inventory :8081/:9091, SpiceDB :50051
   ```

2. A local koku database with the tenant schema for your test org:

   ```bash
   make docker-up-db   # Postgres on :15432 by default
   python koku/manage.py migrate_schemas --shared
   python koku/manage.py shell -c "
   from api.iam.models import Tenant
   t, _ = Tenant.objects.get_or_create(schema_name='org1234567')
   t.create_schema(check_if_exists=True)"
   ```

3. The org must be opted into RBAC v2 (writes are blocked before this):

   ```bash
   curl -X PATCH -H "x-rh-identity: $ADMIN_IDENTITY" \
        -H 'Content-Type: application/json' -d '{"v2_opted_in":true}' \
        http://localhost:9080/api/rbac/v1/tenant/opt-in/
   ```

## Run

```bash
export BASE=http://localhost:9080/api/rbac/v2
export IDENTITY="$(printf '%s' '{"identity":{"account_number":"1234567","org_id":"1234567","type":"User","user":{"username":"admin","user_id":"u-admin","is_org_admin":true}}}' | base64)"

./scripts/rbac_v2_lab/seed.sh        # workspaces, groups, roles, bindings
./scripts/rbac_v2_lab/access_map.py  # prints the user.access map koku computes
```

Start koku with the v2 backend:

```bash
export RBAC_BACKEND=v2
export RBAC_V2_SERVICE_PROTOCOL=http
export RBAC_V2_SERVICE_HOST=localhost
export RBAC_V2_SERVICE_PORT=9080
export RBAC_V2_SERVICE_PATH=/api/rbac/v2
export RBAC_V2_SERVICE_IDENTITY="$IDENTITY"   # unscoped binding reads are admin-gated
export RBAC_V2_RESOURCE_ID_FIELD=name         # lab workspaces are named after the resource ids
python koku/manage.py runserver 0.0.0.0:8002
```

Expected matrix (org `1234567`, workspaces named `123456789012` and `abc-123`):

| Request | user1 (account + cluster) | user2 (cluster only) |
|---|---|---|
| `/api/v1/reports/openshift/costs/` | 200 | 200 |
| `/api/v1/reports/aws/costs/` | 200 | 403 |
| `/api/v1/reports/openshift/infrastructures/aws/costs/` | 200 | 403 |

## Notes

- `RBAC_V2_RESOURCE_ID_FIELD=name` is a lab shortcut. Production needs a Cost-side
  `workspace_id` mapping and `id`.
- `RBAC_BACKEND` is process-wide; a per-tenant rollout needs an Unleash flag (or
  equivalent) resolved per `org_id`, plus a cache generation on flip.
- With `cost-management` removed from `V2_MIGRATION_APP_EXCLUDE_LIST`, v1
  `/access/` returns 400 for v2 orgs; there is no v1 fallback.
