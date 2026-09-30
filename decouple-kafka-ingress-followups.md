# Ingress staging follow-up changes

Changes required before `cost-management.backend.ingress-staging-listener` is enabled in stage or production.

Related design: [decouple-kafka-ingress.md](decouple-kafka-ingress.md).

Current flow:

1. [`handle_message`](koku/masu/external/kafka_msg_handler.py) looks up `Customer` and, when the flag is on, calls [`stage_ingress_payload`](koku/masu/external/downloader/ocp/ingress_staging.py).
2. The listener downloads the tarball, peeks at `manifest.json`, writes `ingress_staging/{org_id}/{cluster_id}/YYYY/MM/DD/{request_id}.tar.gz`, upserts [`IngressStagingPayload`](koku/reporting_common/models.py), and best-effort enqueues the worker.
3. The listener confirms ingress and commits Kafka.
4. [`process_staged_ingress_payload`](koku/masu/processor/ocp/staged_payloads/process_staged.py) claims the row, reads the object back, and runs extract plus line items.
5. [`reconcile_ingress_staging`](koku/masu/external/downloader/ocp/ingress_staging.py) runs every minute and enqueues rows the eager handoff did not finish.

Keep the listener sequence, the `request_id` idempotency gate, S3-before-row ordering, and the rule that a broker enqueue failure must not rewind Kafka. The items below are the gaps in that design.

---

## 1. Fence the staging claim

**Problem.** [`INGRESS_STAGING_LEASE`](koku/masu/external/downloader/ocp/ingress_staging.py) is two hours. [`process_staged_ingress_payload`](koku/masu/processor/ocp/staged_payloads/process_staged.py) has no Celery time limit and does not extend `claimed_at` while it runs. A slow Hive or line-item run is still alive when the lease expires. The reconciler enqueues a second task, that task claims the same row, and both run extract, parquet, and partition sync.

[`_mark_processed`](koku/masu/external/downloader/ocp/ingress_staging.py) and [`_release_for_retry`](koku/masu/external/downloader/ocp/ingress_staging.py) save `state` with no ownership check. Whichever worker finishes last overwrites the other. A late failure can replace `processed` with `failed` or `pending`. Each reclaim also increments `attempts`, so a slow success can hit `settings.MAX_UPDATE_RETRIES` (5) and be marked failed while a worker is still writing.

**Change.**

- Store the claim timestamp (or a generation integer) when [`claim_ingress_staging_row`](koku/masu/external/downloader/ocp/ingress_staging.py) wins the `UPDATE`.
- Pass that token into the worker. Heartbeat `claimed_at` for the life of the task.
- Set a Celery soft time limit below the lease so a hung task is killed before another worker can claim.
- Finish with a conditional update: `WHERE request_id = %s AND claimed_at = %s` (or the generation column). A worker that loses the compare-and-set must not write `processed`, `pending`, or `failed`.
- Stop marking a row `failed` inside the claim function. Exhausted retries belong in the release path, under the same fencing check.

**Files.** [`ingress_staging.py`](koku/masu/external/downloader/ocp/ingress_staging.py), [`process_staged.py`](koku/masu/processor/ocp/staged_payloads/process_staged.py), [`models.py`](koku/reporting_common/models.py) if a generation column is added. A new column on `IngressStagingPayload` needs a follow-up migration; nullable, and not in the same deploy as code that requires it.

**Tests.**

- Two claims while the lease is valid: the second returns without processing.
- Lease expiry while the first worker is still inside processing: the second claim wins, and the first worker's `_mark_processed` / `_release_for_retry` does not change the row.
- A reclaim does not increment `attempts` for a claim the worker still holds.

---

## 2. Stop the reconciler from re-enqueueing the same row

**Problem.** [`_claimable_request_ids`](koku/masu/external/downloader/ocp/ingress_staging.py) selects pending rows older than [`INGRESS_STAGING_BEAT_GRACE`](koku/masu/external/downloader/ocp/ingress_staging.py) (one minute) and processing rows past the lease. [`reconcile_ingress_staging`](koku/masu/external/downloader/ocp/ingress_staging.py) publishes those ids every minute and does not remove them from the eligible set. When workers fall behind, the same `request_id` is queued once a minute until something claims it. Duplicates no-op after the first claim, but they occupy the `ingress` queue ahead of other payloads. The beat comment in [`celery.py`](koku/koku/celery.py) says this task claims rows. It only enqueues them.

**Change.**

- When the reconciler successfully enqueues a row, move it out of the eligible set. Either set `not_before` past the next beat, or record a `queued` state / `enqueued_at` and skip rows already handed off.
- If that enqueue is lost, the row must become eligible again. Use the same lease window as a dropped worker, not another one-minute republish.
- Fix the beat comment so it matches the task.

**Files.** [`ingress_staging.py`](koku/masu/external/downloader/ocp/ingress_staging.py), [`celery.py`](koku/koku/celery.py), [`docs/architecture/celery-tasks.md`](docs/architecture/celery-tasks.md).

**Tests.** Extend [`test_ingress_staging.py`](koku/masu/test/external/downloader/ocp/test_ingress_staging.py): two reconcile runs without a claim enqueue each stale `request_id` once.

---

## 3. Split extract from line-item work, and isolate the queue

**Problem.** [`process_staged_ingress_payload`](koku/masu/processor/ocp/staged_payloads/process_staged.py) runs extract, CSV split, Hive DDL, partition sync, and line items in one task on [`IngressQueue.DEFAULT`](koku/common/queues.py) (`ingress`). That queue is consumed by the default OCP worker (`ocp,ingress` in [`deploy/clowdapp.yaml`](deploy/clowdapp.yaml) and [`deploy/kustomize/patches/worker-ocp.yaml`](deploy/kustomize/patches/worker-ocp.yaml)) and by the scheduler (`SCHEDULER_WORKER_QUEUE` includes `ingress`). There is no xl or penalty variant. One large or penalty-box cluster blocks every other staged payload, and the scheduler pod can run a full Trino job. Customer fairness already exists as `get_customer_queue(schema, OCPQueue)`.

**Change.**

- Keep `ingress` for claim, S3 download, and extract.
- After extract, enqueue line-item processing with `get_customer_queue(schema, OCPQueue)` so xl and penalty customers stay on those workers.
- Remove `ingress` from `SCHEDULER_WORKER_QUEUE`. Beat only needs to publish `reconcile_ingress_staging`. The OCP worker already consumes `ingress`.
- Mark the staging row `processed` only after line-item work for that `request_id` has finished or been intentionally skipped (unknown cluster, retention). A handoff to the OCP queue is not completion.

**Files.** [`process_staged.py`](koku/masu/processor/ocp/staged_payloads/process_staged.py), [`processing.py`](koku/masu/processor/ocp/staged_payloads/processing.py), [`queues.py`](koku/common/queues.py), [`deploy/clowdapp.yaml`](deploy/clowdapp.yaml), [`deploy/kustomize/patches/scheduler.yaml`](deploy/kustomize/patches/scheduler.yaml), [`deploy/kustomize/patches/worker-ocp.yaml`](deploy/kustomize/patches/worker-ocp.yaml).

**Tests.** The staged task enqueues report work on the customer OCP queue and does not call `_process_report_file` inline. Scheduler queue list does not contain `ingress`.

---

## 4. Alert when a confirmed payload never becomes cost data

**Problem.** The listener sends ingress `success` once the tarball and staging row are durable. That is the agreed contract. After five worker failures the row stays `failed`, the object remains in the bucket, and no second validation is sent. [`INGRESS_BACKLOG`](koku/masu/prometheus_stats.py) reports Celery queue depth. It does not report rows sitting in `pending` or `failed`, or age since `stored_at`.

**Change.**

- Add gauges for the count of `pending` and `failed` staging rows, and for the age of the oldest unprocessed row (`now - stored_at`).
- Log permanent failure at error with `request_id`, `org_id`, `cluster_id`, `s3_key`, and `attempts`. Do not log `payload`.
- Page or alert on `state=failed`. A validated upload with no line items is otherwise invisible.

**Files.** [`prometheus_stats.py`](koku/masu/prometheus_stats.py), [`ingress_staging.py`](koku/masu/external/downloader/ocp/ingress_staging.py).

---

## 5. Drop identity material and expire staged objects

**Problem.** `IngressStagingPayload.payload` stores the Kafka value, including `b64_identity`, so [`ROSReportShipper`](koku/masu/external/ros_report_shipper.py) can run on the worker. Nothing clears that column, deletes processed rows, or expires `ingress_staging/` objects. The public table and database backups keep identity tokens. The minutely reconciler scan grows with the table. The claim index is `(state, not_before)`; the lease query filters `claimed_at`, which is not indexed.

**Change.**

- Null `payload` after ROS no longer needs `b64_identity` (once the worker has shipped or skipped ROS for that request).
- Delete or archive `processed` rows on a retention window, and expire the raw tarball on the same window. Keep `failed` rows and their objects until an operator replays or drops them.
- Index `(state, claimed_at)` for lease reclaim, or include `claimed_at` in the claim index.

**Files.** [`models.py`](koku/reporting_common/models.py), [`0046_ingressstagingpayload.py`](koku/reporting_common/migrations/0046_ingressstagingpayload.py) or a follow-up migration, [`process_staged.py`](koku/masu/processor/ocp/staged_payloads/process_staged.py), a small periodic task next to the reconciler.

---

## 6. Make the listener download interruptible

**Problem.** [`download_payload`](koku/masu/external/downloader/ocp/download.py) calls `requests.get(url)` with no timeout and writes `response.content`, so the full tarball sits in listener memory. A hung download holds the single consumer thread. The watchdog logs and does not cancel the request. `max.poll.interval.ms` is 18 minutes, so the group can rebalance while that thread is still blocked.

Commit still depends on Postgres: the `Customer` lookup in [`handle_message`](koku/masu/external/kafka_msg_handler.py), then the staging read and upsert. Those queries are short. An `OperationalError` or `InterfaceError` rewinds. A `ProgrammingError` (migration `0046` not applied) does not. [`listen_for_messages`](koku/masu/external/kafka_msg_handler.py) logs that exception and continues, and a later successful commit can skip the offset.

[`is_permanent_download_error`](koku/masu/external/downloader/ocp/download.py) treats every HTTP 4xx as final, including 408 and 429.

**Change.**

- Stream the quarantine response to the temp file. Set a connect and read timeout.
- Treat 408 and 429 as rewindable. Keep other 4xx, including a gone quarantine object, as confirm-failure.
- Map `ProgrammingError` on the staging read/upsert to `KafkaMsgHandlerError` so the consumer rewinds instead of moving on.
- Apply migration `0046` before any schema has the flag on.

**Files.** [`download.py`](koku/masu/external/downloader/ocp/download.py), [`ingress_staging.py`](koku/masu/external/downloader/ocp/ingress_staging.py), [`kafka_msg_handler.py`](koku/masu/external/kafka_msg_handler.py).

**Tests.** A 429 raises `KafkaMsgHandlerError`. A 404 returns `FAILURE_CONFIRM_STATUS`. A `ProgrammingError` from the staging upsert rewinds.

---

## 7. Decide how on-prem enables the flag

**Problem.** [`handle_message`](koku/masu/external/kafka_msg_handler.py) calls the flag with `dev_fallback=True`. That fallback is true only when the Unleash environment is `development`. On-prem uses `MockUnleashClient`, and `cost-management.backend.ingress-staging-listener` is not in `ONPREM_FLAG_DEFAULTS` ([`feature_flags.py`](koku/koku/feature_flags.py)). SaaS can enable the flag per schema. An on-prem production listener stays on [`legacy_message_processing`](koku/masu/external/kafka_msg_handler.py).

**Change.** If on-prem should take this path, add the flag to `ONPREM_FLAG_DEFAULTS` with the intended default and ship that separately from the SaaS rollout. If on-prem stays on the legacy listener until a later release, say so in [decouple-kafka-ingress.md](decouple-kafka-ingress.md) and in the module comment on `legacy_message_processing`.

---

## 8. Make the worker path readable

**Problem.** The state machine is split across packages, and private names are the API. [`process_staged.py`](koku/masu/processor/ocp/staged_payloads/process_staged.py) imports `_mark_processed` and `_release_for_retry` from the downloader. [`extract_payload`](koku/masu/processor/ocp/staged_payloads/processing.py) deletes the temp directory on several paths, and `process_staged` deletes it again in `finally`. Line-item processing uses the copy under `INSIGHTS_LOCAL_REPORT_DIR`, so the first delete is safe, but it is not obvious. [`docs/architecture/csv-processing-ocp.md`](docs/architecture/csv-processing-ocp.md) still describes daily files as `{report_type}.{day}.{manifest_id}.{counter}.csv` taken under a `report_tracker` row lock. [`_day_slice_csv_name`](koku/masu/processor/ocp/staged_payloads/processing.py) hashes the slice and does not take that lock.

**Change.**

- Rename the finish helpers to public `mark_processed` and `release_for_retry`, and keep them next to `claim_ingress_staging_row`.
- Leave temp-directory cleanup to the caller that created the directory (`stage_ingress_payload` and `process_staged_ingress_payload`).
- Update the CSV architecture doc to the content-hash filename: `{report_type}.{day}.{manifest_id}.{digest}.csv`.

---

## Suggested order

| Order | Item | Why first |
|-------|------|-----------|
| 1 | Fence the claim | Concurrent workers can corrupt `state` and double-write line items |
| 2 | Reconciler eligibility | Queue amplification shows up as soon as workers lag |
| 3 | Queue split and scheduler | One tenant can block the pool, and the scheduler can run Trino |
| 4 | Failure metrics | Confirmed uploads can fail silently |
| 5 | Retention and `claimed_at` index | Table growth and identity retention |
| 6 | Streaming download and 408/429 | Remaining listener stalls |
| 7 | On-prem flag decision | Avoid a rollout that does not apply where it was intended |
| 8 | Names, cleanup, doc | Safe to do with any of the above |

## Tests already in place

These cover the listener contract and should keep passing:

- Staging flag confirms without `extract_payload` or `process_report` ([`test_kafka_msg_handler.py`](koku/masu/test/external/test_kafka_msg_handler.py)).
- A redelivered `request_id` does not upload a second object.
- A staging upsert failure after S3 raises `KafkaMsgHandlerError`.
- A broker error after the row is stored still confirms.
- A second claim loses while the lease is held ([`test_ingress_staging.py`](koku/masu/test/external/downloader/ocp/test_ingress_staging.py)).
- A replay of a completed report file does not call `process_report` again ([`test_process_staged.py`](koku/masu/test/processor/ocp/staged_payloads/test_process_staged.py)).
- Day-slice names are stable and do not lock the manifest ([`test_divide_csv_daily`](koku/masu/test/external/test_kafka_msg_handler.py)).
