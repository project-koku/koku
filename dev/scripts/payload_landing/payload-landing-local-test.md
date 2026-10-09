# Testing Through Payload Landing

Design: [`docs/architecture/payload_landing.md`](../../../docs/architecture/payload_landing.md).

**Goal:** With `cost-management.backend.ingress-staging-listener` on, the listener stores the tarball in S4 and commits Kafka while Postgres or Trino is down. Cost data catches up after that service returns.

**Stack:** SaaS (`ONPREM=False` in `.env`) with Trino/S4 **and** Kafka. Use the Docker Compose profile **`payload_landing`** (`make docker-up-payload-landing`). The on-prem-only stack has no Trino/S4, so it cannot exercise this split.

**Tenant:** `org1234567` / account `10001` / cluster `my-ocp-cluster-1`. Use a **new** `request_id` per scenario (same id only recopies the S4 receipt).

### Helpers (repo root)

| Step | Prefer |
|------|--------|
| Start SaaS + Kafka + beat + listener + ingress worker | `make docker-up-payload-landing` (or `make docker-up-payload-landing-no-build`) |
| Migrations / test customer | `make run-migrations`, `make create-test-customer` |
| Publish Kafka announce | `make publish-hccm-upload request_id=…` |
| Verify lag, S4, PG, listener logs | `make payload-landing-status` |
| Build tarball / HTTP serve / pending retry | `dev/scripts/payload_landing/build_ingress_payload_tar.sh`, `serve_ingress_payload.sh`, `retry_ingress_staging.sh` |
| Tear down (incl. profile services) | `make docker-down` |

---

## 1. Start the stack

From the koku repo root, env setup:

```
ONPREM=False
DEVELOPMENT=True
S3_ACCESS_KEY=s4admin
S3_SECRET=s4secret
POSTGRES_SQL_SERVICE_PORT=15432
```

Now run these commands:

```bash
make docker-up-payload-landing
make run-migrations
make create-test-customer
```

`docker-up-payload-landing` is the SaaS min stack plus Kafka (`init-kafka` topics), `koku-beat`, `koku-listener`, and `ingress-worker`.

---

## 2. Publish one upload

Build a tarball whose `manifest.json` has `cluster_id` `my-ocp-cluster-1` and dates within `RETAIN_NUM_MONTHS` (default four). Nise writes under `--insights-upload`; tar **one** `YYYYMMDD-YYYYMMDD` folder so `manifest.json` is at the archive root.

**Quick path** (from repo root; `pipenv install` if `pipenv run nise` is missing):

```bash
dev/scripts/payload_landing/build_ingress_payload_tar.sh -s 2026-09-01 -e 2026-09-30

# Leave the next command running in the terminal
dev/scripts/payload_landing/serve_ingress_payload.sh

make publish-hccm-upload request_id=req-baseline-1
make payload-landing-status
```

Adjust `-s` / `-e` in the build script to your window.

Confirm the listener can reach the tarball (project name `koku` → network `koku_default`):

```bash
docker run --rm --network koku_default curlimages/curl:latest \
  -sfI "http://host.docker.internal:8765/payload.tar.gz" | head -3
```

Optional overrides: `make publish-hccm-upload request_id=req-1 url=http://host.docker.internal:8765/payload.tar.gz account=10001 org_id=1234567`

Header **`service:hccm`** is required on the Kafka message (`make publish-hccm-upload` wraps [`publish_hccm_upload.sh`](publish_hccm_upload.sh)).

With `DEVELOPMENT=True`, validation to `platform.upload.validation` is skipped. At `KOKU_LOG_LEVEL=INFO`, expect `Processing message offset` and `ingress payload stored for registration` in `docker logs koku_listener`.

Sanitized keys for `req-baseline-1` use stem `reqbaseline1` under `data/ingress_staging/`.

### Manual build and publish

See [`build_ingress_payload_tar.sh`](build_ingress_payload_tar.sh) for the nise/tar steps, or run them by hand:

```bash
pipenv run python dev/scripts/render_nise_yamls.py \
  -f dev/scripts/nise_ymls/ocp_on_aws/ocp_static_data.yml \
  -o /tmp/ocp_static_data.yml -s 2026-09-01 -e 2026-09-30
mkdir -p /tmp/nise_ocp_output
S3_ACCESS_KEY=s4admin S3_SECRET_KEY=s4secret S3_BUCKET_NAME=ocp-ingress \
  pipenv run nise report ocp \
  --static-report-file /tmp/ocp_static_data.yml \
  --ocp-cluster-id my-ocp-cluster-1 \
  --insights-upload /tmp/nise_ocp_output \
  --daily-reports
MONTH_DIR=$(find /tmp/nise_ocp_output/my-ocp-cluster-1 -mindepth 1 -maxdepth 1 -type d | head -1)
mkdir -p /tmp/ingress-payloads
COPYFILE_DISABLE=1 tar czf /tmp/ingress-payloads/payload.tar.gz -C "$MONTH_DIR" $(ls -A "$MONTH_DIR")
```

---

## 3. Baseline (everything up)

With beat, ingress worker, listener, Postgres, and Trino up, publish a new id (or reuse checks from §2). Pass when:

1. Listener logs `ingress payload stored for registration` (no `Seeking back`).
2. `hccm-group` lag on `platform.upload.announce` is 0.
3. Tar, receipt, and pending marker appear in S4; pending clears after register.
4. Row reaches `processed`, `payload_cleared` is true; ingress worker logs `staged ingress payload processed`.
5. Trino lists tenant tables.

```bash
make payload-landing-status
docker compose exec trino trino --catalog hive --schema org1234567 --execute "SHOW TABLES"
```

---

## 4. Postgres stopped

Stop DB only after listener, beat, and ingress worker are running (do not recreate the listener while Postgres is down).

```bash
docker compose stop db
make publish-hccm-upload request_id=req-pg-down-1
make publish-hccm-upload request_id=req-pg-down-2
make payload-landing-status
```

Pass when both messages stage to S4, offsets commit (lag 0), and listener does not `Seeking back` for those offsets. PG rows appear after `docker compose start db` and the next `reconcile_ingress_staging` minute (register runs inside that beat task).

---

## 5. Trino stopped

From a healthy stack:

```bash
docker compose stop trino hive-metastore
make publish-hccm-upload request_id=req-trino-down-1
make payload-landing-status
```

Pass immediately on Kafka/S4 staging. Row may sit `pending`/`processing` with line-item errors until Trino is back:

```bash
docker compose start hive-metastore trino
docker compose up -d --wait --no-deps trino
```

To retry without waiting on backoff (only when row is `pending`):

```bash
dev/scripts/payload_landing/retry_ingress_staging.sh req-trino-down-1
```

---

## 6. Outage expectations

| Check | Postgres stopped | Trino stopped |
|---|---|---|
| Listener stores tar, receipt, pending marker | Yes | Yes |
| Offset commits, lag 0 | Yes | Yes |
| Staging row during outage | After PG returns | Yes; line items wait |
| Cost data in Trino during outage | No | No |

S4 is on the listener path: stop `s4-path-proxy`, publish once, expect `Seeking back` and no commit — then start the proxy again.

Restore before leaving:

```bash
docker compose start db hive-metastore trino s4-path-proxy
```

Stop the full stack (including Kafka and `ingress-worker`):

```bash
make docker-down
```
