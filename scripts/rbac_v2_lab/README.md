# RBAC v2 lab

Reproduces the experimental `RBAC_BACKEND=v2` path: koku reads RBAC v2 role
bindings (instead of `/api/rbac/v1/access/`), keeps permission evaluation local,
and maps workspaces to the concrete resource ids it already scopes reports by.

Design and decisions: [`docs/architecture/rbac-v2-kessel/README.md`](../../docs/architecture/rbac-v2-kessel/README.md).

## What runs where

| Port | Service | Notes |
|---|---|---|
| 9080 | RBAC v2 | Kessel compose stack |
| 8081 / 9091 | Inventory API | HTTP / gRPC |
| 50051 | SpiceDB | gRPC |
| 9092 | Kafka | |
| 8083 | Kafka Connect | |
| 15432 | RBAC Postgres | **owned by the Kessel stack** |
| 15434 | koku Postgres | lab override, so the two do not collide |
| 8002 | koku | 8000 is the Relations API in the stack |

## Prerequisites

- Docker or Podman with the `compose` plugin, plus `yq`, `curl`, `jq`
- A koku dev environment (`pipenv install --dev`, or the repo's container)
- `python3` for `access_map.py`

On Apple Silicon the stack's images are amd64 and run under emulation; start-up
is slower, and RBAC needs ~1 CPU.

## 1. Start the Kessel stack

```bash
git clone https://github.com/project-kessel/inventory-api.git
cd inventory-api
make kessel-up      # add --profile monitoring if you want Grafana
```

Wait for Kafka (~60 s) and check:

```bash
curl -sf http://localhost:8081/api/kessel/v1/livez
curl -sf http://localhost:9080/api/rbac/v1/status/
curl -sf http://localhost:8083/connectors
```

`make kessel-compose-integration-test` is a good end-to-end smoke test if you
have `kcat`, `grpcurl`, and `jq`.

> [!tip] If the stack is unhealthy after a Docker restart
> `make kessel-down && make kessel-up` recreates the missing containers
> (SpiceDB/Kafka Connect are the usual casualties).

## 2. Create the koku database and tenant schema

The Kessel stack already binds 15432, so run koku's database on 15434:

```bash
POSTGRES_SQL_SERVICE_PORT=15434 make docker-up-db
. scripts/rbac_v2_lab/env.sh

python koku/manage.py migrate_schemas --shared
python koku/manage.py shell -c "
from api.iam.models import Tenant
t, _ = Tenant.objects.get_or_create(schema_name='org1234567')
t.create_schema(check_if_exists=True)"
```

`create_schema()` verifies `template0` and clones it; the first run applies all
tenant migrations to `template0` and can take several minutes.

> [!warning] A GET request does not create a tenant
> koku's middleware only persists a customer on a write request. If the schema is
> missing you will see `Tenant does not exist ... schema: org1234567` and a 404
> from the report endpoints. The command above is the supported way to create it.

## 3. Opt the org into RBAC v2

v2 writes are blocked until the tenant opts in; the state is irreversible.

```bash
. scripts/rbac_v2_lab/env.sh

curl -s -X PATCH \
  -H "x-rh-identity: ${ADMIN_IDENTITY}" \
  -H 'Content-Type: application/json' \
  -d '{"v2_opted_in":true}' \
  "${RBAC_URL}/api/rbac/v1/tenant/opt-in/"

curl -s -H "x-rh-identity: ${ADMIN_IDENTITY}" \
  "${RBAC_URL}/api/rbac/v1/tenant/opt-in/"   # {"v2_opted_in":true}
```

The first request after opt-in bootstraps the tenant; the RBAC consumer needs a
moment (about a second locally) before v2 reads succeed.

## 4. Seed the worked example

Two sources, two users:

- `user1` — AWS account `123456789012` **and** OCP cluster `abc-123`, read/write
- `user2` — OCP cluster `abc-123` only, read-only

```bash
. scripts/rbac_v2_lab/env.sh
./scripts/rbac_v2_lab/seed.sh          # workspaces, groups, roles, bindings
./scripts/rbac_v2_lab/access_map.py    # prints the access map koku computes
```

`seed.sh` is idempotent: it reuses workspaces, groups, and roles by name and
replaces the role set per `(group, workspace)` via
`PUT /role-bindings/by-subject/`.

> [!note] The seeded catalog has `*`, not `read`
> For report resource types the stage catalog exposes `cost-management:<type>:*`
> only; creating a v2 role with `:read` fails with `PermissionsNotFoundError`.
> The seed therefore uses `*` (koku maps it to `read` for report types) and
> `cost_model:read` for the read-only example. See the design's platform asks.

## 5. Run koku against RBAC v2

```bash
. scripts/rbac_v2_lab/env.sh
python koku/manage.py runserver 0.0.0.0:8002
```

`env.sh` sets the database (15434), Redis, `RBAC_BACKEND=v2`, the v2 service
address, the service identity for the admin-gated binding read, and
`RBAC_V2_RESOURCE_ID_FIELD=name`.

Note the URL prefix: this repo serves `/api/v1/…` (from `API_PATH_PREFIX`), not
`/api/cost-management/v1/…`.

## 6. Verify

```bash
./scripts/rbac_v2_lab/verify.sh
```

Expected:

| Request (`/api/v1/…`) | user1 | user2 |
|---|---|---|
| `reports/openshift/costs/` | 200 | 200 |
| `reports/aws/costs/` | 200 | 403 |
| `reports/openshift/infrastructures/aws/costs/` | 200 | 403 |

Raw calls look like:

```bash
curl -s -H "x-rh-identity: ${USER2_IDENTITY}" \
  "http://localhost:8002/api/v1/reports/aws/costs/?filter%5Btime_scope_value%5D=-1&filter%5Btime_scope_units%5D=month&filter%5Bresolution%5D=monthly"
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| 403 with `Not entitled` | the identity needs `entitlements.cost_management.is_entitled: true`; `env.sh` includes it for user1/user2 |
| 404 `Tenant does not exist` | schema missing — step 2; remember GET does not create it |
| 400 `V2 orgs may only query applications...` | expected: the org is opted into v2 and `cost-management` is not in `V2_MIGRATION_APP_EXCLUDE_LIST`; koku must use `RBAC_BACKEND=v2` |
| `PermissionsNotFoundError` on role create | `:read` is not seeded in the catalog; use `*` for report types |
| 403 on `/v2/role-bindings` | unscoped reads are admin-gated; set `RBAC_V2_SERVICE_IDENTITY` to an org-admin identity |
| Connection refused on 15434 | `POSTGRES_SQL_SERVICE_PORT=15434 make docker-up-db` |
| Report IDs do not match | `RBAC_V2_RESOURCE_ID_FIELD` must be `name` while the lab workspaces are named after the ids |
| 424 from koku | RBAC unreachable; koku treats RBAC failures as failed dependency |
| `make kessel-up` fails: `.../inventory-api.yaml: Is a directory` | a previous run bind-mounted a missing file and Docker created a directory; `rmdir "${TMPDIR:-/tmp}/inventory-api-full-kessel/inventory-api.yaml"` and retry |
| `make kessel-up` fails: Kafka exits with `NodeExistsException` | stale ZooKeeper broker registration in a restarted container; `docker rm -f full-kessel-zookeeper-1 full-kessel-kafka-1 full-kessel-kafka-connect-1` then rerun `make kessel-up` |

## Cleanup

```bash
# stop koku
pkill -f "manage.py runserver 0.0.0.0:8002"
# stop the stack
(cd inventory-api && make kessel-down)
# optional: stop the koku database
docker stop koku-db
```

## Notes

- `RBAC_V2_RESOURCE_ID_FIELD=name` is a lab shortcut. Production needs a
  Cost-side `workspace_id` mapping and `id`.
- `RBAC_BACKEND` is process-wide; a per-tenant rollout needs an Unleash flag (or
  equivalent) resolved per `org_id`, plus a cache generation on flip.
- The opt-in is one-way. With `cost-management` removed from
  `V2_MIGRATION_APP_EXCLUDE_LIST` there is no v1 fallback for that org.
