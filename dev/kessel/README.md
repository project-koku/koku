# Kessel Local Stack for Integration Testing

This directory contains a Podman/Docker Compose stack that runs the full
Kessel authorization platform locally for contract-level integration tests
against Koku's ReBAC backend.

## Components

| Service            | Image                                         | Container Port | Host Port | Purpose                                        |
|--------------------|-----------------------------------------------|----------------|-----------|------------------------------------------------|
| `database`         | `postgres:16`                                 | 5432           | **5433**  | Shared PostgreSQL for SpiceDB + Inventory API  |
| `spicedb-migrate`  | `authzed/spicedb:latest`                      | --             | --        | One-shot: runs SpiceDB DB migrations           |
| `spicedb`          | `authzed/spicedb:latest`                      | 50051          | **50051** | SpiceDB authorization engine (gRPC)            |
| `relations-api`    | `kessel-relations:latest`                     | 8000 / 9000    | **8100** / **9100** | Kessel Relations API (HTTP + gRPC)  |
| `inventory-api`    | `kessel-inventory:latest`                     | 8000 / 9000    | **8081** / **9081** | Kessel Inventory API (HTTP + gRPC) |
| `inventory-migrate`| `kessel-inventory:latest`                     | --             | --        | One-shot: runs Inventory DB migrations         |

### Port Collision Avoidance

The host port assignments are chosen to avoid conflicts with co-running
Koku services:

- **Relations API HTTP: 8100** (not 8000) -- `kessel-admin.sh` uses REST
  endpoints at this port for tuple management.
- **Relations API gRPC: 9100** (not 9000) -- Koku/ROS Prometheus metrics
  exports on port 9000 by default.
- **PostgreSQL: 5433** (not 5432) -- avoids conflict with a host PostgreSQL
  or the Koku test database container (which typically uses 15432).
- **Inventory HTTP: 8081** (not 8000) -- Koku's Django dev server uses 8000.

## Prerequisites

- **Podman >= 4.0** with `podman compose` (or Docker Compose v2)
- **Network**: The compose file creates its own bridge network (`kessel`),
  no external network is required.

## Quick Start

```bash
# Start the stack (from koku repo root)
podman compose -f dev/kessel/docker-compose.yml up -d

# Verify all services are healthy
podman compose -f dev/kessel/docker-compose.yml ps

# Seed the Cost Management roles into Kessel (uses seed-roles.yaml via zed CLI)
./dev/kessel/deploy-kessel.sh

# Run contract tests
KESSEL_INVENTORY_HOST=localhost \
KESSEL_INVENTORY_PORT=9081 \
ONPREM=True \
.venv-test/bin/python -m pytest koku/koku_rebac/test/test_contract.py -v

# Tear down
podman compose -f dev/kessel/docker-compose.yml down -v
```

## Configuration Files

| File                   | Purpose                                                 |
|------------------------|----------------------------------------------------------|
| `docker-compose.yml`   | Service definitions and port mappings                   |
| `.env`                 | Environment variables (preshared key, DB credentials)   |
| `schema.zed`           | SpiceDB/ZED authorization schema for Cost Management    |
| `inventory-config.yaml`| Inventory API server configuration                      |
| `resource-schemas/`    | Kessel Inventory API resource type schemas (10 types)   |

## Environment Variables for Koku

When running Koku code (tests or the dev server) against this local
Kessel stack, set these environment variables:

| Variable                 | Value        | Notes                                             |
|--------------------------|--------------|---------------------------------------------------|
| `ONPREM`                 | `True`       | Activates `AUTHORIZATION_BACKEND=rebac`           |
| `KESSEL_INVENTORY_HOST`  | `localhost`  | gRPC host for Inventory API                       |
| `KESSEL_INVENTORY_PORT`  | `9081`       | Mapped from container port 9000                   |
| `KESSEL_RELATIONS_URL`   | `http://localhost:8100` | HTTP/REST -- used by `kessel-admin.sh`  |
| `ENHANCED_ORG_ADMIN`     | `False`      | Disable admin bypass to exercise Kessel auth path |

## ZED Schema

The `schema.zed` file defines the Cost Management authorization model
for SpiceDB. It maps 1:1 with the role definitions in
[`seed-roles.yaml`](./seed-roles.yaml).

The schema defines:
- **12 cost-management relations** on `rbac/role` (AWS, GCP, Azure,
  OpenShift, Cost Model, Settings -- read/write)
- **Intersected permissions** on `rbac/role_binding` (subject AND
  granted role must both have the relation)
- **Hierarchical workspace permissions** (inherited from parent workspaces)
- **Group membership** (`rbac/group` with nested group support)

When the schema changes, update both `schema.zed` and the
role definitions in `seed-roles.yaml`.

## Resource Schemas

The `resource-schemas/` directory contains Kessel Inventory API resource
type definitions for all 10 Cost Management resource types. These are
loaded by the Inventory API at startup via `inventory-config.yaml`
(`schema.in-memory.type: dir`).

Each resource type has:
- `config.yaml` -- resource type name and allowed reporters
- `common_representation.json` -- JSON Schema for shared fields (workspace_id)
- `reporters/cost_management/config.yaml` -- reporter metadata
- `reporters/cost_management/<type>.json` -- reporter-specific JSON Schema

Resource types: `openshift_cluster`, `openshift_node`, `openshift_project`,
`aws_account`, `aws_organizational_unit`, `gcp_account`, `gcp_project`,
`azure_subscription_guid`, `cost_model`, `settings`.

### ReportResource Tuple Limitation

The local dev compose does **not** include Kafka, Debezium, or the
Inventory Consumer. `ReportResource` writes to Inventory's Postgres but
does **not** create tuples in SpiceDB. For IT/CT tests, use Relations
API `CreateTuples` as a test helper to create the authorization tuples
that the full pipeline would produce in production.

## Troubleshooting

### SpiceDB fails to start
Check that the `spicedb-migrate` container completed successfully:
```bash
podman compose -f dev/kessel/docker-compose.yml logs spicedb-migrate
```

### Relations API rejects tuples
The schema loaded by Relations API (via `SPICEDB_SCHEMA_FILE`) must
define every relation referenced in `seed-roles.yaml`. Check the
Relations API logs:
```bash
podman compose -f dev/kessel/docker-compose.yml logs relations-api
```

### Port already in use
If port 9100 is occupied, override it in the compose file or use an
environment variable override:
```bash
RELATIONS_HOST_PORT=9200 podman compose -f dev/kessel/docker-compose.yml up -d
```
(This requires adding `${RELATIONS_HOST_PORT:-9100}:9000` to the compose
file's `relations-api.ports`.)
