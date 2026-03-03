# Kessel Development Guide

How to set up and develop Koku with Kessel (ReBAC) authorization locally.
Kessel is the authorization backend for on-prem deployments, replacing the
SaaS RBAC service which is not available outside of cloud.redhat.com.

## Prerequisites

- Python 3.11+ with [Pipenv](https://pipenv.pypa.io/)
- Podman >= 4.0 with `podman compose` (or Docker Compose v2)
- A working Koku development environment ([Getting Started](../../../README.md))

---

## 1. Start the Kessel Stack

```bash
podman compose -f dev/kessel/docker-compose.yml up -d
```

This starts:

| Service | Host Port | Purpose |
|---|---|---|
| PostgreSQL | 5433 | Shared database for SpiceDB + Inventory |
| SpiceDB | 50051 | Authorization engine (gRPC) |
| Relations API | 9100 (gRPC), 8100 (HTTP) | Kessel Relations API |
| Inventory API | 9081 (gRPC), 8081 (HTTP) | Kessel Inventory API -- the endpoint Koku connects to |

The ZED schema is loaded automatically from `dev/kessel/schema.zed` via the
`SPICEDB_SCHEMA_FILE` environment variable on the Relations API container.

Wait for services to be healthy:

```bash
podman compose -f dev/kessel/docker-compose.yml ps
```

See [`dev/kessel/README.md`](../../../dev/kessel/README.md) for port collision
rationale and infrastructure details.

---

## 2. Run Koku Against Kessel

Set the environment variables to point Koku at the local Kessel stack:

```bash
export ONPREM=True                          # Forces AUTHORIZATION_BACKEND=rebac
export KESSEL_INVENTORY_HOST=localhost
export KESSEL_INVENTORY_PORT=9081
export ENHANCED_ORG_ADMIN=False             # Disable admin bypass to exercise Kessel auth
```

Then start Koku as you normally would. With `ONPREM=True`, the `resolve_authorization_backend`
function in `koku_rebac/config.py` selects the `rebac` backend. All RBAC checks flow through
the Kessel Inventory API (`Check`, `StreamedListObjects`) instead of the platform RBAC service.

**TLS behavior:** When `KESSEL_CA_PATH` is empty (the default), Koku connects using
plaintext gRPC (matching the docker-compose stack). When a CA path is set, TLS is
enabled. In production, set `KESSEL_CA_PATH` to the appropriate certificate.

> **Note:** On-prem deployments always use Kessel. There is no "switch back to RBAC"
> because the SaaS RBAC service is not available outside of cloud.redhat.com. The
> `AUTHORIZATION_BACKEND` variable is set automatically by `ONPREM=True` and should
> not be overridden manually in on-prem environments.

---

## 3. Run Tests

Kessel tests are gated behind the `ENABLE_KESSEL_TEST` environment variable.
Tests that require the live Kessel stack are skipped unless this variable is set.

All live-stack tests seed their own fixtures programmatically via
[`KesselFixture`](../../../koku/koku_rebac/test/kessel_fixture.py) -- no manual
provisioning is needed.

### Unit tests (no stack needed)

Unit tests mock gRPC calls and do not require the Kessel stack:

```bash
pipenv run python -m pytest koku/koku_rebac/test/test_client.py \
    koku/koku_rebac/test/test_config.py \
    koku/koku_rebac/test/test_models.py \
    koku/koku_rebac/test/test_hooks.py \
    koku/koku_rebac/test/test_urls.py \
    koku/koku_rebac/test/test_workspace.py \
    koku/koku_rebac/test/test_access_provider.py \
    koku/koku_rebac/test/test_resource_reporter.py \
    koku/koku_rebac/test/test_middleware_rebac.py -v
```

### Contract tests (stack must be running)

Contract tests validate gRPC calls against the live Kessel stack:

```bash
ENABLE_KESSEL_TEST=True \
KESSEL_INVENTORY_HOST=localhost \
KESSEL_INVENTORY_PORT=9081 \
ONPREM=True \
pipenv run python -m pytest koku/koku_rebac/test/test_contract.py -v
```

### Integration tests (stack must be running)

Integration tests exercise the middleware and access provider against live Kessel:

```bash
ENABLE_KESSEL_TEST=True \
ONPREM=True \
pipenv run python koku/manage.py test koku_rebac.test.test_integration -v 2
```

### E2E regression tests (stack must be running)

E2E tests exercise full Koku views with Kessel authorization:

```bash
ENABLE_KESSEL_TEST=True \
ONPREM=True \
pipenv run python koku/manage.py test koku_rebac.test.test_e2e_regression -v 2
```

---

## 4. Modify the ZED Schema

The local schema lives at `dev/kessel/schema.zed`. The **source of truth** for the
production schema is [`RedHatInsights/rbac-config`](https://github.com/RedHatInsights/rbac-config).

To apply schema changes:

1. Edit `dev/kessel/schema.zed`
2. Restart the Relations API to reload:

```bash
podman compose -f dev/kessel/docker-compose.yml restart relations-api
```

3. Run contract tests to validate the schema resolves correctly:

```bash
ENABLE_KESSEL_TEST=True KESSEL_INVENTORY_HOST=localhost KESSEL_INVENTORY_PORT=9081 ONPREM=True \
pipenv run python -m pytest koku/koku_rebac/test/test_contract.py -v
```

When the schema changes, also update the role definitions in
[`dev/kessel/seed-roles.yaml`](../../../dev/kessel/seed-roles.yaml) to stay in sync.

---

## 5. Full On-Prem Stack (Kessel + Kafka + Sources)

The Kessel stack (Section 1) covers **authorization only**. A full on-prem
environment also needs Kafka and the sources-client for provider lifecycle
management (create / update / destroy sources, Kafka event publishing).

When `ONPREM=True`, source destroy events are published to Kafka via
`publish_application_destroy_event()` so downstream services (e.g.
ros-ocp-backend) are notified. If Kafka is not running, these publishes
will fail.

**When you need the full stack:**
- Testing the sources CRUD flow end-to-end
- Testing provider create / destroy lifecycle with Kafka events
- Validating that ros-ocp-backend receives source events from Koku

**Start the full on-prem stack:**

```bash
# 1. Start the Kessel authorization stack
podman compose -f dev/kessel/docker-compose.yml up -d

# 2. Start Koku services with the onprem profile (includes Kafka + sources-client)
podman compose --profile onprem up -d
```

The `onprem` profile in the root `docker-compose.yml` adds:

| Service | Port | Purpose |
|---|---|---|
| Zookeeper | 2181 | Kafka coordination |
| Kafka | 29092 | Event streaming (sources events, ingestion) |
| init-kafka | -- | One-shot topic creation |

The `sources-client` container (always defined, not profile-gated) connects to
Kafka and the external Sources API. It runs `manage.py sources`, which starts
the Kafka consumer thread for `platform.sources.event-stream`.

Set both Kessel and Kafka environment variables:

```bash
export ONPREM=True
export KESSEL_INVENTORY_HOST=localhost
export KESSEL_INVENTORY_PORT=9081
export ENHANCED_ORG_ADMIN=False
export INSIGHTS_KAFKA_HOST=localhost
export INSIGHTS_KAFKA_PORT=29092
```

If you only need to work on Kessel authorization (middleware, access checks,
permissions), you can skip the `--profile onprem` services and just run the
Kessel stack from Section 1.

---

## 6. Tear Down

```bash
# Kessel stack only
podman compose -f dev/kessel/docker-compose.yml down -v

# Full on-prem stack (Kafka + Koku services)
podman compose --profile onprem down -v
```

The `-v` flag removes volumes (database data). Omit it to preserve data between runs.

---

## 7. Environment Variable Reference

| Variable | Default | Purpose |
|---|---|---|
| `ONPREM` | `False` | When `True`, forces `AUTHORIZATION_BACKEND=rebac`. On-prem always sets this to `True`. |
| `AUTHORIZATION_BACKEND` | `rbac` | Set automatically by `ONPREM`; do not override manually in on-prem environments |
| `KESSEL_INVENTORY_HOST` | `localhost` | Inventory API gRPC host |
| `KESSEL_INVENTORY_PORT` | `9081` | Inventory API gRPC port |
| `KESSEL_CA_PATH` | `""` | Path to CA cert for TLS; empty = plaintext/insecure |
| `KESSEL_RELATIONS_URL` | `http://localhost:8100` | Relations API HTTP base URL |
| `KESSEL_CACHE_TIMEOUT` | `300` | Access cache TTL in seconds |
| `ENHANCED_ORG_ADMIN` | `False` | Org admin bypass; docker-compose overrides to `True` for convenience. Set `False` to exercise Kessel auth. |
| `ENABLE_KESSEL_TEST` | (unset) | Any non-empty value enables live-stack tests (e.g. `True`) |
| `INSIGHTS_KAFKA_HOST` | `kafka` | Kafka broker host (set to `localhost` when running outside compose) |
| `INSIGHTS_KAFKA_PORT` | `29092` | Kafka broker port |
| `KAFKA_CONNECT` | `True` | Enables Kafka connectivity in Koku |
| `SOURCES_API_SVC_HOST` | `sources-server` | Platform Sources API host |
| `SOURCES_API_SVC_PORT` | `3000` | Platform Sources API port |

---

## 8. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `connection refused` on port 9081 | Inventory API not ready | Wait: `podman compose -f dev/kessel/docker-compose.yml ps` |
| `Check` returns `ALLOWED_FALSE` | Missing tuples in the chain | Verify the full chain: role has `t_*_read` → principal, role_binding has `t_granted` → role and `t_subject` → principal, tenant has `t_default_binding` → role_binding |
| `StreamedListObjects` returns empty | Resource not linked to workspace | Verify `t_workspace` tuple exists on the resource |
| CT/IT/E2E skipped with "Kessel stack not available" | `ENABLE_KESSEL_TEST` not set | Set `ENABLE_KESSEL_TEST=True` |
| Kessel auth not exercised (admin gets full access without tuples) | `ENHANCED_ORG_ADMIN=True` (docker-compose default) bypasses Kessel for admin users | Set `ENHANCED_ORG_ADMIN=False` to exercise the Kessel auth path |
| TLS handshake error on startup | `KESSEL_CA_PATH` set but stack uses plaintext | Unset `KESSEL_CA_PATH` for local dev |
| Schema changes not taking effect | Relations API caches schema | Restart: `podman compose -f dev/kessel/docker-compose.yml restart relations-api` |
| Source destroy fails / Kafka publish error | Kafka not running | Start Kafka: `podman compose --profile onprem up -d kafka` |
| `sources-client` can't connect to Kafka | Wrong Kafka host/port | Set `INSIGHTS_KAFKA_HOST=localhost` and `INSIGHTS_KAFKA_PORT=29092` |

---

## References

- Infrastructure details: [`dev/kessel/README.md`](../../../dev/kessel/README.md)
- Architecture docs: [`docs/architecture/kessel-integration/`](./)
- Detailed design: [`kessel-ocp-detailed-design.md`](./kessel-ocp-detailed-design.md)
- ZED schema delta: [`zed-schema-upstream-delta.md`](./zed-schema-upstream-delta.md)
- Test fixture helper: [`koku/koku_rebac/test/kessel_fixture.py`](../../../koku/koku_rebac/test/kessel_fixture.py)
- Kessel SDK: [`kessel-sdk`](https://pypi.org/project/kessel-sdk/) (>= 2.1.0)
- Production ZED schema: [RedHatInsights/rbac-config](https://github.com/RedHatInsights/rbac-config)
