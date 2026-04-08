# Detailed Design: Kafka-Based Resource Reporting to Kessel

| Field         | Value                                                                 |
|---------------|-----------------------------------------------------------------------|
| Jira          | TBD                                                                   |
| Parent story  | [FLPATH-2690](https://issues.redhat.com/browse/FLPATH-2690)          |
| HLD           | [kessel-ocp-integration.md](./kessel-ocp-integration.md)              |
| Author        | Jordi Gil                                                             |
| Status        | Draft                                                                 |
| Created       | 2026-03-12                                                           |
| Last updated  | 2026-03-12                                                           |

## Table of Contents

1. [Overview and Scope](#1-overview-and-scope)
2. [Context and Motivation](#2-context-and-motivation)
3. [Architecture](#3-architecture)
4. [Kafka Topic Schema](#4-kafka-topic-schema)
5. [Producer Changes (resource_reporter.py)](#5-producer-changes)
6. [Consumer Design](#6-consumer-design)
7. [Caller Inventory](#7-caller-inventory)
8. [Deployment](#8-deployment)
9. [Reliability Analysis](#9-reliability-analysis)
10. [Migration and Rollout](#10-migration-and-rollout)
11. [Testing Strategy](#11-testing-strategy)
12. [Risks and Mitigations](#12-risks-and-mitigations)

---

## 1. Overview and Scope

This document describes a change to how Koku reports resources (integrations,
clusters, nodes, projects, accounts, subscriptions) to Kessel. The current
synchronous approach — where `resource_reporter.py` calls the Kessel Inventory
API (gRPC) and Relations API (REST) inline during request processing — is
replaced by an asynchronous Kafka-based pipeline:

1. **Koku** publishes resource lifecycle events to a Kafka topic.
2. A **standalone consumer** reads events and calls Kessel APIs with guaranteed
   delivery (infinite retry with exponential backoff).

This change is scoped to the **resource reporting path only** (Sources API
integration registration, data pipeline resource discovery, retention cleanup).
It does not affect the authorization read path (`KesselAccessProvider`), the
ReBAC Bridge management plane, or any SaaS behavior.

### 1.1 What Changes

- `resource_reporter.py` stops making synchronous Kessel API calls. It
  publishes events to Kafka via the existing `confluent_kafka` producer.
- A new Go consumer binary reads from the topic and calls Kessel Inventory API
  (gRPC) + Relations API (gRPC) with infinite retry.
- The `KesselSyncedResource` Django model is removed. Kafka offset tracking
  replaces application-level sync status.

### 1.2 What Does NOT Change

- `KesselAccessProvider` — still reads from Kessel gRPC directly.
- `_filter_by_integration_access` — still queries `StreamedListObjects`.
- Sources API CRUD — still writes to Koku's PostgreSQL.
- ReBAC Bridge design — still uses direct gRPC for admin management.
- SaaS behavior — `AUTHORIZATION_BACKEND=rbac` short-circuits all reporting;
  no events are published.

---

## 2. Context and Motivation

### 2.1 Current Design

`resource_reporter.py` calls Kessel APIs synchronously during:

- Source creation (`ProviderBuilder.create_provider_from_source`)
- Data pipeline summarization (OCP nodes/projects, AWS accounts/OUs, Azure
  subscriptions, GCP accounts/projects)
- Source deletion (`DestroySourceMixin.destroy`)
- Retention cleanup (`cleanup_orphaned_kessel_resources`)

These calls are best-effort: gRPC/HTTP errors are logged but never propagated
to the caller. When Kessel is unavailable, `KesselSyncedResource` records
`kessel_synced=False`, but **nothing retries the failed operation**. The
resource remains invisible to non-wildcard users via `StreamedListObjects`
until a manual reconciler (not yet implemented) re-syncs it.

### 2.2 Problems with the Current Approach

1. **No automatic retry.** A transient Kessel outage during source creation
   or data ingestion leaves resources permanently unsynced unless manually
   detected and corrected.

2. **Synchronous latency in the request path.** Source creation pays
   50-200ms for the Kessel gRPC + Relations API REST calls (more under load
   or if Kessel is slow). This latency is unnecessary — the admin doesn't
   need Kessel to be updated before the HTTP response returns.

3. **Tracking overhead.** The `KesselSyncedResource` model, its migration,
   and the `update_or_create` calls on every resource event add Django ORM
   overhead that exists only to compensate for the lack of retry.

4. **Data pipeline amplification.** During OCP summarization, Koku may
   report dozens of nodes and projects in a tight loop
   (`_report_ocp_resources_to_kessel`). Each `on_resource_created` call
   blocks on a gRPC + REST round-trip. With Kafka, these become fast
   in-process publishes.

### 2.3 Why Kafka

Koku already deploys Kafka in the on-prem profile for the
`platform.sources.event-stream` topic (Sources lifecycle events consumed by
ROS). The infrastructure — Kafka broker, Zookeeper, topic management via
`init-kafka` — is already operational. Adding a new topic and a lightweight
consumer reuses this investment without introducing new infrastructure.

Kafka provides:

- **Durable buffering**: messages survive producer and consumer restarts.
- **Guaranteed delivery**: manual offset commit ensures at-least-once
  processing. Combined with `upsert: true` on `CreateTuples`, the pipeline
  is effectively idempotent.
- **Automatic retry**: the consumer retries indefinitely with exponential
  backoff when Kessel is unavailable. No application-level tracking needed.
- **Ordering**: messages keyed by `org_id` maintain per-org ordering within
  a partition.

### 2.4 Why Not CDC / Debezium

The [kessel-stack](https://github.com/akoserwal/kessel-stack) project
demonstrates a CDC-based approach where Debezium captures PostgreSQL WAL
changes and routes them through Kafka to consumers. This was evaluated and
rejected for this use case because:

- Koku's resource reporting is not a projection from an authoritative
  PostgreSQL table. The application already knows what to report — it just
  needs a durable delivery mechanism.
- CDC requires Kafka Connect, Debezium connectors, `wal_level=logical`
  reconfiguration, replication slots, and outbox tables. Direct Kafka
  publishing from the application avoids all of this.
- The kessel-stack CDC pipeline adds 2-15 seconds of latency; direct Kafka
  publishing is ~5ms.

---

## 3. Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ WRITE PATH (async via Kafka)                                        │
│                                                                     │
│  Sources API ──┐                                                    │
│  OCP Pipeline ─┤                                                    │
│  AWS Pipeline ─┤──→ resource_reporter.py ──→ Kafka ──→ Consumer     │
│  Azure Pipeline┤      (publish event)        topic     (Go binary)  │
│  GCP Pipeline ─┤                                          │         │
│  Middleware ────┘                                          ▼         │
│                                              ┌────────────────────┐ │
│                                              │ Kessel gRPC        │ │
│                                              │  • Inventory API   │ │
│                                              │    (ReportResource, │ │
│                                              │     DeleteResource) │ │
│                                              │  • Relations API   │ │
│                                              │    (CreateTuples,   │ │
│                                              │     DeleteTuples)   │ │
│                                              └────────────────────┘ │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ READ PATH (direct, synchronous — unchanged)                         │
│                                                                     │
│  Koku middleware ──→ Kessel Inventory API gRPC                      │
│  Sources list    ──→   (Check, StreamedListObjects)                 │
│                                                                     │
│  SpiceDB = single source of truth                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow: Source Creation

```
Admin POST /sources/
  │
  ├─→ Django serializer saves Source to PostgreSQL           ✅ committed
  ├─→ ProviderBuilder.create_provider_from_source()
  │     └─→ on_resource_created("openshift_cluster", ...)
  │           └─→ publish to kessel.resource.events          ✅ ~5ms
  │     └─→ on_resource_created("integration", ...)
  │           └─→ publish to kessel.resource.events          ✅ ~5ms
  │     └─→ create_structural_tuple(...)
  │           └─→ publish to kessel.resource.events          ✅ ~5ms
  └─→ Return 201 to admin

Consumer (async, seconds later):
  ├─→ Read "create" event from Kafka
  ├─→ Call Inventory API gRPC: ReportResource                ✅ or retry
  ├─→ Call Relations API gRPC: CreateTuples (t_workspace)    ✅ or retry
  └─→ Commit Kafka offset                                   ✅
```

### 3.3 Data Flow: Source Deletion

```
Admin DELETE /sources/{id}/
  │
  ├─→ ProviderBuilder.destroy_provider()                     ✅
  ├─→ publish_application_destroy_event()  (ROS Kafka, unchanged)
  ├─→ on_resource_deleted("integration", ...)
  │     └─→ publish to kessel.resource.events                ✅ ~5ms
  └─→ Return 204 to admin

Consumer (async):
  ├─→ Read "delete" event from Kafka
  ├─→ Call Inventory API gRPC: DeleteResource                ✅ or retry
  ├─→ Call Relations API gRPC: DeleteTuples (all tuples)     ✅ or retry
  └─→ Commit offset                                         ✅
```

### 3.4 Data Flow: Pipeline Resource Discovery

```
Celery worker: OCP summarization
  │
  └─→ _report_ocp_resources_to_kessel(provider, cluster_id, nodes, projects)
        ├─→ for each node:  publish "create" event           ✅ ~5ms each
        ├─→ for each project:
        │     ├─→ publish "create" event                     ✅
        │     └─→ publish "create_structural_tuple" event    ✅
        └─→ (no blocking gRPC calls in the pipeline)
```

---

## 4. Kafka Topic Schema

### 4.1 Topic Configuration

| Property | Value |
|---|---|
| Topic name | `kessel.resource.events` |
| Partitions | 3 |
| Replication factor | 1 (single-broker on-prem) |
| Retention | 168 hours (7 days) |
| Message key | `org_id` (ensures per-org ordering within a partition) |
| Compression | none (matches existing Koku Kafka config) |

### 4.2 Event Schema

All events share a common envelope with an `action` discriminator:

```json
{
  "action": "create | delete | create_structural_tuple | delete_all_tuples",
  "resource_type": "openshift_cluster",
  "resource_id": "cluster-prod-01",
  "org_id": "1234567",
  "timestamp": "2026-03-12T14:30:00Z"
}
```

#### Action: `create`

Reports a resource to Kessel Inventory and creates the primary `t_workspace`
tuple in SpiceDB.

```json
{
  "action": "create",
  "resource_type": "openshift_cluster",
  "resource_id": "cluster-prod-01",
  "org_id": "1234567",
  "timestamp": "2026-03-12T14:30:00Z"
}
```

Consumer behavior:
1. Call `ReportResource` on Inventory API (gRPC).
2. Call `CreateTuples` on Relations API (gRPC) with:
   `cost_management/{type}:{id} #t_workspace → rbac/workspace:{org_id}`.
3. Both calls use `upsert` / idempotent semantics.

#### Action: `delete`

Removes a resource from Kessel Inventory and deletes all its SpiceDB tuples.

```json
{
  "action": "delete",
  "resource_type": "integration",
  "resource_id": "source-uuid-123",
  "org_id": "1234567",
  "timestamp": "2026-03-12T15:00:00Z"
}
```

Consumer behavior:
1. Call `DeleteResource` on Inventory API (gRPC).
2. Call `DeleteTuples` on Relations API (gRPC) with filter:
   `resource_namespace=cost_management, resource_type={type},
   resource_id={id}` (deletes all relations: `t_workspace`,
   `has_cluster`, `has_project`, etc.).

#### Action: `create_structural_tuple`

Creates a cross-type relationship tuple (e.g., `integration#has_cluster`,
`openshift_cluster#has_project`). No Inventory API call — tuple only.

```json
{
  "action": "create_structural_tuple",
  "resource_type": "integration",
  "resource_id": "source-uuid-123",
  "relation": "has_cluster",
  "subject_type": "openshift_cluster",
  "subject_id": "cluster-prod-01",
  "org_id": "1234567",
  "timestamp": "2026-03-12T14:30:01Z"
}
```

Consumer behavior:
1. Call `CreateTuples` on Relations API (gRPC) with:
   `cost_management/{resource_type}:{resource_id} #{relation} →
   cost_management/{subject_type}:{subject_id}`.

#### Action: `delete_all_tuples`

Deletes all SpiceDB tuples for a resource without touching the Inventory API.
Used by `cleanup_orphaned_kessel_resources` when a provider's cost data has
been fully purged and the tracked Kessel resources need cleanup.

```json
{
  "action": "delete_all_tuples",
  "resource_type": "openshift_node",
  "resource_id": "node-01",
  "org_id": "1234567",
  "timestamp": "2026-03-12T16:00:00Z"
}
```

Consumer behavior:
1. Call `DeleteResource` on Inventory API (gRPC) — best effort, may already
   be gone.
2. Call `DeleteTuples` on Relations API (gRPC) with resource filter.

### 4.3 Schema Validation

The consumer validates events before processing:

| Field | Required | Validation |
|---|---|---|
| `action` | Yes | Must be one of the four defined actions |
| `resource_type` | Yes | Must be in `IMMEDIATE_WRITE_TYPES` |
| `resource_id` | Yes | Non-empty string |
| `org_id` | Yes | Non-empty string |
| `relation` | Only for `create_structural_tuple` | Non-empty string |
| `subject_type` | Only for `create_structural_tuple` | Non-empty string |
| `subject_id` | Only for `create_structural_tuple` | Non-empty string |

Malformed messages (JSON parse failure or missing required fields) are logged
and skipped — the offset is committed so the consumer does not block on
unparseable messages. These are programming errors, not transient failures.

---

## 5. Producer Changes

### 5.1 resource_reporter.py

The module's public API (`on_resource_created`, `on_resource_deleted`,
`create_structural_tuple`, `cleanup_orphaned_kessel_resources`) is preserved.
Callers require no changes. The internal implementation changes from
synchronous Kessel API calls to Kafka event publishing.

#### New: `_publish_kessel_event`

```python
import json
from django.utils import timezone
from kafka_utils.utils import get_producer, delivery_callback

KESSEL_EVENTS_TOPIC = "kessel.resource.events"

def _publish_kessel_event(event: dict) -> None:
    """Publish a resource lifecycle event to the Kessel events topic."""
    event.setdefault("timestamp", timezone.now().isoformat())
    producer = get_producer()
    producer.produce(
        KESSEL_EVENTS_TOPIC,
        key=event["org_id"],
        value=json.dumps(event).encode("utf-8"),
        callback=delivery_callback,
    )
    producer.poll(0)
```

#### Changed: `on_resource_created`

```python
def on_resource_created(resource_type: str, resource_id: str, org_id: str) -> None:
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return

    _publish_kessel_event({
        "action": "create",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "org_id": org_id,
    })
```

#### Changed: `on_resource_deleted`

```python
def on_resource_deleted(resource_type: str, resource_id: str, org_id: str) -> None:
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return

    _publish_kessel_event({
        "action": "delete",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "org_id": org_id,
    })
```

#### Changed: `create_structural_tuple`

The function signature gains an `org_id` parameter (used as the Kafka message
key for per-org ordering). The two existing callers already have `org_id`
available in scope:

- `ProviderBuilder._report_integration` — has `self.org_id`
- `ocp_report_db_accessor._report_ocp_resources_to_kessel` — has `org_id`

```python
def create_structural_tuple(
    resource_type: str, resource_id: str, relation: str,
    subject_type: str, subject_id: str, org_id: str = "",
) -> bool:
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return True

    _publish_kessel_event({
        "action": "create_structural_tuple",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "relation": relation,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "org_id": org_id,
    })
    return True
```

Callers update to pass `org_id`:

```python
# ProviderBuilder._report_integration
create_structural_tuple("integration", source_uuid, "has_cluster",
                        "openshift_cluster", cluster_id, org_id=self.org_id)

# ocp_report_db_accessor._report_ocp_resources_to_kessel
create_structural_tuple("openshift_cluster", cluster_id, "has_project",
                        "openshift_project", project_name, org_id=org_id)
```

#### Changed: `cleanup_orphaned_kessel_resources`

```python
def cleanup_orphaned_kessel_resources(provider_uuid: str, org_id: str) -> int:
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return 0

    from api.models import Provider

    if Provider.objects.filter(uuid=provider_uuid).exists():
        return 0

    tracked = KesselSyncedResource.objects.filter(org_id=org_id)
    if not tracked.exists():
        return 0

    count = 0
    for entry in tracked.iterator():
        _publish_kessel_event({
            "action": "delete",
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "org_id": org_id,
        })
        entry.delete()
        count += 1

    return count
```

> **Note on `cleanup_orphaned_kessel_resources`**: This function still reads
> `KesselSyncedResource` to know which resources to delete. During the
> migration period (see [section 10](#10-migration-and-rollout)), the tracking
> table remains for cleanup of resources that were synced before the Kafka
> migration. Once all pre-migration resources have been cleaned up or expired,
> the model can be removed entirely. New resources created after the migration
> do not write to the tracking table.

### 5.2 Removed: Synchronous Kessel Calls

The following functions are removed from `resource_reporter.py`:

- `_build_report_request` — ReportResource proto construction (moves to consumer)
- `_create_resource_tuples` — Relations API REST POST (moves to consumer)
- `_get_tuples_url` — Relations API URL builder (moves to consumer)
- `_build_delete_request` — DeleteResource proto construction (moves to consumer)
- `_delete_from_kessel` — Inventory API gRPC DeleteResource (moves to consumer)
- `_delete_resource_tuples` — Relations API REST DELETE (moves to consumer)
- `_track_synced_resource` — KesselSyncedResource ORM call (no longer needed)
- `get_kessel_client` import — no longer needed in the producer

### 5.3 Removed: KesselSyncedResource Model

After the migration period (all pre-migration tracked resources expired or
cleaned up), the `KesselSyncedResource` model and its migration
(`0001_initial.py`) are removed. Kafka's offset tracking replaces
application-level sync status.

### 5.4 Topic Registration in init-kafka

The `init-kafka` service in `docker-compose.yml` is updated to create the new
topic:

```bash
kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists \
  --topic kessel.resource.events --replication-factor 1 --partitions 3
```

---

## 6. Consumer Design

### 6.1 Overview

A standalone Go binary that:

1. Subscribes to the `kessel.resource.events` Kafka topic.
2. Deserializes and validates each event.
3. Calls Kessel Inventory API (gRPC) and/or Relations API (gRPC) based on
   the event action.
4. Commits the Kafka offset only after successful processing.
5. Retries indefinitely with exponential backoff on transient failures.
6. Exposes Prometheus metrics for monitoring.

### 6.2 Kafka Consumer Configuration

| Setting | Value | Rationale |
|---|---|---|
| `Consumer.Offsets.AutoCommit.Enable` | `false` | Manual commit after successful processing |
| `Consumer.Offsets.Initial` | `OffsetOldest` | Process all unprocessed messages on first startup |
| `Consumer.Group.Rebalance.Strategy` | `RoundRobin` | Even partition distribution |
| `Version` | `V3_0_0_0` | Matches Koku's Kafka broker (cp-kafka 7.8.6) |
| `Consumer.Return.Errors` | `true` | Surface consumer errors for logging |

### 6.3 Processing Loop

```go
func (h *Handler) ConsumeClaim(session sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
    for msg := range claim.Messages() {
        h.processWithRetry(msg)
        session.MarkMessage(msg, "")
        session.Commit()
    }
    return nil
}
```

The offset is committed only after `processWithRetry` returns, which only
happens on success. If the pod crashes at any point before `Commit()`, Kafka
re-delivers the message.

### 6.4 Retry Strategy

```go
func (h *Handler) processWithRetry(msg *sarama.ConsumerMessage) {
    attempt := 0
    maxBackoff := 5 * time.Minute
    baseBackoff := 1 * time.Second

    for {
        err := h.processEvent(msg)
        if err == nil {
            return
        }

        attempt++
        backoff := min(baseBackoff * (1 << (attempt - 1)), maxBackoff)
        jitter := time.Duration(rand.Float64() * 0.4 - 0.2) * backoff
        time.Sleep(backoff + jitter)
    }
}
```

- **Infinite retry**: the loop never exits on error. If Kessel is down for
  hours, the consumer waits.
- **Exponential backoff**: 1s → 2s → 4s → ... → capped at 5 minutes.
- **Jitter**: ±20% to prevent thundering herd on recovery.
- **Per-partition blocking**: while retrying one message, subsequent messages
  on that partition queue up. With 3 partitions and org_id-based keying, a
  stuck message blocks only one org's events.

### 6.5 Event Processing

```go
func (h *Handler) processEvent(msg *sarama.ConsumerMessage) error {
    var event ResourceEvent
    if err := json.Unmarshal(msg.Value, &event); err != nil {
        log.Printf("skipping malformed message at offset %d: %v", msg.Offset, err)
        return nil  // skip, don't retry malformed messages
    }

    if err := event.Validate(); err != nil {
        log.Printf("skipping invalid event at offset %d: %v", msg.Offset, err)
        return nil
    }

    switch event.Action {
    case "create":
        return h.handleCreate(event)
    case "delete":
        return h.handleDelete(event)
    case "create_structural_tuple":
        return h.handleCreateStructuralTuple(event)
    case "delete_all_tuples":
        return h.handleDeleteAllTuples(event)
    default:
        log.Printf("skipping unknown action %q at offset %d", event.Action, msg.Offset)
        return nil
    }
}
```

### 6.6 Kessel API Calls

The consumer uses **gRPC** (not REST) for both Kessel APIs. This differs from
the current `resource_reporter.py` which uses gRPC for Inventory and REST for
Relations. gRPC provides proper error codes, streaming support, and connection
multiplexing.

#### handleCreate

```go
func (h *Handler) handleCreate(event ResourceEvent) error {
    // 1. ReportResource on Inventory API
    req := buildReportResourceRequest(event)
    if _, err := h.inventoryClient.ReportResource(ctx, req); err != nil {
        return fmt.Errorf("ReportResource failed: %w", err)
    }

    // 2. CreateTuples on Relations API (t_workspace)
    tuples := buildWorkspaceTuples(event)
    if _, err := h.relationsClient.CreateTuples(ctx, &pb.CreateTuplesRequest{
        Upsert: true,
        Tuples: tuples,
    }); err != nil {
        return fmt.Errorf("CreateTuples failed: %w", err)
    }

    return nil
}
```

#### handleDelete

```go
func (h *Handler) handleDelete(event ResourceEvent) error {
    // 1. DeleteResource on Inventory API (may already be gone — non-fatal)
    req := buildDeleteResourceRequest(event)
    if _, err := h.inventoryClient.DeleteResource(ctx, req); err != nil {
        if status.Code(err) != codes.NotFound {
            return fmt.Errorf("DeleteResource failed: %w", err)
        }
    }

    // 2. DeleteTuples on Relations API (all tuples for this resource)
    filter := buildResourceFilter(event)
    if _, err := h.relationsClient.DeleteTuples(ctx, &pb.DeleteTuplesRequest{
        Filter: filter,
    }); err != nil {
        if status.Code(err) != codes.NotFound {
            return fmt.Errorf("DeleteTuples failed: %w", err)
        }
    }

    return nil
}
```

#### handleCreateStructuralTuple

```go
func (h *Handler) handleCreateStructuralTuple(event ResourceEvent) error {
    tuples := buildStructuralTuples(event)
    if _, err := h.relationsClient.CreateTuples(ctx, &pb.CreateTuplesRequest{
        Upsert: true,
        Tuples: tuples,
    }); err != nil {
        return fmt.Errorf("CreateTuples (structural) failed: %w", err)
    }

    return nil
}
```

### 6.7 gRPC Client Configuration

| Setting | Value |
|---|---|
| Inventory API target | `KESSEL_INVENTORY_URL` env var (e.g., `kessel-inventory-api:9000`) |
| Relations API target | `KESSEL_RELATIONS_URL` env var (e.g., `kessel-relations-api:9000`) |
| TLS | Disabled (`grpc.WithTransportCredentials(insecure.NewCredentials())`) for on-prem |
| Auth (JWT) | Optional — `KESSEL_TOKEN_ENDPOINT`, `KESSEL_CLIENT_ID`, `KESSEL_CLIENT_SECRET` env vars. When set, the consumer obtains a JWT and attaches it as a gRPC metadata header. Same mechanism as `kessel_auth.py` in Koku. |
| Keepalive | 30s ping interval, 10s timeout |
| Max message size | 4 MB (default) |

### 6.8 Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `kessel_consumer_events_processed_total` | Counter | `action`, `resource_type`, `status` | Total events processed |
| `kessel_consumer_processing_duration_seconds` | Histogram | `action` | Per-event processing latency |
| `kessel_consumer_retry_attempts_total` | Counter | `action` | Total retry attempts |
| `kessel_consumer_validation_errors_total` | Counter | — | Malformed/invalid events skipped |

### 6.9 Health Checks

| Probe | Mechanism |
|---|---|
| Liveness | File-based: `/tmp/kubernetes-liveness` exists while consumer is running |
| Readiness | Consumer group has joined and partitions are assigned |

### 6.10 Graceful Shutdown

On `SIGTERM`/`SIGINT`:
1. Cancel the context — stops consuming new messages.
2. Current in-flight message completes processing (or is abandoned if mid-retry
   sleep — offset not committed, Kafka re-delivers).
3. Consumer group session is closed — Kafka rebalances partitions.
4. Health check file is removed.

---

## 7. Caller Inventory

All callers of `resource_reporter.py` public functions. Only
`create_structural_tuple` callers require a minor change (adding `org_id`).
All other function signatures are preserved.

| Caller | Function | Resource types | Trigger |
|---|---|---|---|
| `ProviderBuilder._report_ocp_resource` | `on_resource_created` | `openshift_cluster` | Source creation (OCP) |
| `ProviderBuilder._report_integration` | `on_resource_created`, `create_structural_tuple` | `integration`, `integration#has_cluster` | Source creation (OCP with source_uuid) |
| `DestroySourceMixin.destroy` | `on_resource_deleted` | `integration` | Source deletion |
| `ocp_report_db_accessor._report_ocp_resources_to_kessel` | `on_resource_created`, `create_structural_tuple` | `openshift_node`, `openshift_project`, `openshift_cluster#has_project` | OCP data summarization |
| `aws/common.py` (update_account_aliases) | `on_resource_created` | `aws_account` | AWS data ingestion |
| `aws_org_unit_crawler` | `on_resource_created` | `aws_account`, `aws_organizational_unit` | AWS org unit crawling |
| `azure_report_parquet_summary_updater` | `on_resource_created` | `azure_subscription_guid` | Azure data summarization |
| `gcp_report_db_accessor` | `on_resource_created` | `gcp_account`, `gcp_project` | GCP topology population |
| `middleware.py` (create_customer) | `on_resource_created` | `settings` | First request from new org |
| `remove_expired._cleanup_kessel_on_expiry` | `cleanup_orphaned_kessel_resources` | All tracked types | Data retention cleanup |

---

## 8. Deployment

### 8.1 Consumer Container

```yaml
# docker-compose.yml (onprem profile)
kessel-resource-consumer:
  build:
    context: ./dev/kessel/consumer
    dockerfile: Dockerfile
  container_name: koku-kessel-resource-consumer
  profiles: ["onprem"]
  depends_on:
    kafka:
      condition: service_healthy
  environment:
    KAFKA_BROKERS: kafka:29092
    KAFKA_GROUP_ID: kessel-resource-consumer
    KAFKA_TOPIC: kessel.resource.events
    KESSEL_INVENTORY_URL: kessel-inventory-api:9000
    KESSEL_RELATIONS_URL: kessel-relations-api:9000
    METRICS_PORT: "9090"
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 128M
        cpu: "0.25"
      reservations:
        memory: 64M
        cpu: "0.1"
```

### 8.2 Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kessel-resource-consumer
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: consumer
          image: quay.io/insights-onprem/kessel-resource-consumer:latest
          resources:
            requests:
              memory: 32Mi
              cpu: 50m
            limits:
              memory: 128Mi
              cpu: 250m
          env:
            - name: KAFKA_BROKERS
              value: kafka:29092
            - name: KAFKA_GROUP_ID
              value: kessel-resource-consumer
            - name: KAFKA_TOPIC
              value: kessel.resource.events
            - name: KESSEL_INVENTORY_URL
              value: kessel-inventory-api.kessel.svc.cluster.local:9000
            - name: KESSEL_RELATIONS_URL
              value: kessel-relations-api.kessel.svc.cluster.local:9000
          livenessProbe:
            exec:
              command: ["test", "-f", "/tmp/kubernetes-liveness"]
            periodSeconds: 10
          readinessProbe:
            exec:
              command: ["test", "-f", "/tmp/kubernetes-readiness"]
            periodSeconds: 10
            initialDelaySeconds: 15
```

### 8.3 Resource Footprint

| Component | Memory | CPU | Notes |
|---|---|---|---|
| Consumer binary (Go) | 32-64 MB | 50m | Single goroutine per partition |
| Kafka topic overhead | ~0 | ~0 | Reuses existing broker |

Total new infrastructure: **one pod, ~32 MB RAM**.

---

## 9. Reliability Analysis

### 9.1 Failure Scenarios

| Scenario | Behavior | Data loss? |
|---|---|---|
| **Kessel down during processing** | Consumer retries with exponential backoff (cap 5m), blocks partition. Messages accumulate in Kafka. | No |
| **Consumer pod crashes during gRPC call** | Offset not committed. Kafka re-delivers on restart. `CreateTuples(upsert=true)` makes replay idempotent. | No |
| **Consumer pod crashes during backoff sleep** | Same as above — offset not committed. | No |
| **Consumer pod crashes after gRPC success, before offset commit** | Re-delivery. `CreateTuples(upsert=true)` is idempotent. `DeleteTuples` for an already-deleted resource returns success or NotFound (handled). | No |
| **Kafka broker restarts** | Consumer reconnects automatically (Sarama handles this). | No |
| **Consumer down for > 7 days** | Kafka retention expires. Oldest unprocessed messages lost. | Yes — mitigated by alerting (see 9.3) |
| **Malformed message** | Logged and skipped. Offset committed. | N/A (programming error) |
| **Kafka producer publish fails** | `confluent_kafka` `delivery_callback` logs the error. The `produce()` call itself is non-blocking; errors surface via callback. Source still saved in PostgreSQL. | Kessel not updated — same as current best-effort behavior, but now visible via delivery callback metrics |

### 9.2 Idempotency

| Action | Idempotent? | Mechanism |
|---|---|---|
| `create` (ReportResource) | Yes | Inventory API treats duplicate reports as updates |
| `create` (CreateTuples) | Yes | `upsert: true` flag |
| `create_structural_tuple` | Yes | `upsert: true` flag |
| `delete` (DeleteResource) | Yes | NotFound is treated as success |
| `delete` (DeleteTuples) | Yes | Deleting non-existent tuples is a no-op |

### 9.3 Monitoring and Alerting

| Alert | Condition | Severity |
|---|---|---|
| Consumer lag > 100 | `kafka_consumergroup_lag{group="kessel-resource-consumer"} > 100` | Warning |
| Consumer lag > 1000 | `kafka_consumergroup_lag{group="kessel-resource-consumer"} > 1000` | Critical |
| Consumer not connected | No heartbeat from consumer group for > 5 minutes | Critical |
| Retry rate high | `rate(kessel_consumer_retry_attempts_total[5m]) > 10` | Warning |

---

## 10. Migration and Rollout

### 10.1 Phases

**Phase 1: Deploy consumer alongside existing synchronous path.**

- Deploy the consumer and create the Kafka topic.
- `resource_reporter.py` continues making synchronous Kessel calls (no
  change). Additionally, it publishes events to Kafka (dual-write).
- The consumer processes events. Kessel receives both the synchronous call
  and the async replay — idempotent, no harm.
- Validates end-to-end event flow without risk.

**Phase 2: Switch to Kafka-only publishing.**

- `resource_reporter.py` stops making synchronous Kessel calls. Only
  publishes to Kafka.
- Consumer is the sole writer to Kessel.
- `KesselSyncedResource` tracking is no longer written for new events.

**Phase 3: Remove synchronous code and tracking model.**

- Remove `_build_report_request`, `_create_resource_tuples`,
  `_delete_from_kessel`, `_delete_resource_tuples`, `_track_synced_resource`,
  `_get_tuples_url`, and all gRPC/REST client code from `resource_reporter.py`.
- Remove `KesselSyncedResource` model and migration after confirming no
  `kessel_synced=False` rows remain.
- Remove `kessel_auth.get_http_auth_headers` if no other callers remain.

### 10.2 Rollback

At any phase, reverting to synchronous calls requires only re-enabling the
removed code in `resource_reporter.py`. The consumer can be stopped without
data loss — messages accumulate in Kafka (retained 7 days) and are processed
when the consumer restarts.

---

## 11. Testing Strategy

### 11.1 Unit Tests (Python — resource_reporter.py)

| # | Test | Description |
|---|---|---|
| P1 | `on_resource_created` publishes event | Mock `get_producer`, verify `produce()` called with correct topic, key, and JSON payload |
| P2 | `on_resource_created` no-op when rbac | `AUTHORIZATION_BACKEND=rbac` → `get_producer` not called |
| P3 | `on_resource_deleted` publishes delete event | Verify `action=delete` in payload |
| P4 | `create_structural_tuple` publishes event | Verify `action=create_structural_tuple` with relation, subject_type, subject_id |
| P5 | `create_structural_tuple` no-op when rbac | No publish when backend is rbac |
| P6 | `cleanup_orphaned_kessel_resources` publishes per tracked resource | Mock `KesselSyncedResource.objects.filter`, verify one event per entry |
| P7 | `_publish_kessel_event` includes timestamp | Verify ISO 8601 timestamp in event |
| P8 | `_publish_kessel_event` uses org_id as key | Verify `key` parameter matches `org_id` |

### 11.2 Unit Tests (Go — consumer)

| # | Test | Description |
|---|---|---|
| C1 | `processEvent` handles create | Mock gRPC stubs, verify ReportResource + CreateTuples called |
| C2 | `processEvent` handles delete | Verify DeleteResource + DeleteTuples called |
| C3 | `processEvent` handles create_structural_tuple | Verify CreateTuples called with correct relation |
| C4 | `processEvent` handles delete_all_tuples | Verify DeleteResource + DeleteTuples called |
| C5 | `processEvent` skips malformed JSON | Return nil (no retry), increment validation error counter |
| C6 | `processEvent` skips missing required fields | Return nil, increment validation error counter |
| C7 | `processEvent` skips unknown action | Return nil |
| C8 | `processWithRetry` retries on gRPC error | Mock gRPC to fail twice then succeed. Verify 3 calls, offset committed. |
| C9 | `processWithRetry` caps backoff at 5 minutes | Verify sleep duration after many failures |
| C10 | `handleDelete` tolerates NotFound | Mock DeleteResource to return NotFound. Verify no error returned. |
| C11 | `handleCreate` builds correct ReportResource proto | Verify inventory_id, type, reporter_type, representations |
| C12 | `handleCreate` builds correct t_workspace tuple | Verify namespace, type, id, relation, subject |

### 11.3 Integration Tests

| # | Test | Description |
|---|---|---|
| I1 | End-to-end create via Kafka | Publish create event → consumer processes → verify resource exists in Kessel Inventory + SpiceDB tuple exists |
| I2 | End-to-end delete via Kafka | Publish delete event → consumer processes → verify resource gone from Inventory + tuples gone |
| I3 | Consumer handles Kessel restart | Publish event, stop Kessel, verify consumer retries, restart Kessel, verify event processed |
| I4 | Consumer handles pod restart | Publish event, kill consumer mid-processing, restart, verify event re-processed |
| I5 | Source creation triggers Kessel sync | POST /sources/ (OCP) → verify Kafka event published → consumer processes → cluster visible via StreamedListObjects |
| I6 | Source deletion triggers cleanup | DELETE /sources/{id}/ → verify Kafka delete event → consumer processes → integration gone from SpiceDB |
| I7 | OCP summarization reports nodes/projects | Trigger OCP summarization → verify create events for nodes and projects → consumer creates resources in Kessel |
| I8 | Ordering preserved per org | Publish create then delete for same resource (same org_id key) → consumer processes in order → resource ends up deleted |

### 11.4 Existing Test Updates

Tests in `test_resource_reporter.py`, `test_hooks.py`, and
`test_middleware_kessel.py` that currently mock `get_kessel_client` and
assert on `ReportResource`/`DeleteResource` gRPC calls are updated to mock
`get_producer` and assert on `produce()` calls instead. The test structure
(one test per caller, one per failure mode) remains the same.

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Consumer down > 7 days, messages expire | Low | Resources not synced to Kessel | Alerting on consumer lag (section 9.3). Consumer is stateless and restarts quickly. |
| Kafka publish fails silently | Low | Same as current best-effort behavior | `delivery_callback` logs errors. Monitor `kafka_producer_delivery_errors_total`. |
| Event ordering violation (create processed after delete) | Very low | Stale resource in Kessel | Org_id-based partitioning ensures per-org ordering. Cross-org ordering is irrelevant. |
| Consumer gRPC auth token expiry during long retry loop | Medium | 401 errors until token refreshed | Consumer refreshes JWT on 401/Unauthenticated gRPC status code. |
| Partition blocked by slow Kessel response | Medium | Other events on same partition delayed | 3 partitions limit blast radius. 30s gRPC timeout per call prevents indefinite hangs. |
| Migration phase 1 dual-write doubles Kessel load | Low | Temporary increase during migration | Kessel handles upserts efficiently. Migration phase is short. |
