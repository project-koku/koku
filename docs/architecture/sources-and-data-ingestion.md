# Sources System and Data Ingestion Architecture

This document describes the Sources system, the Sources listener, and how source creation triggers data ingestion in the Koku application.

## Table of Contents

- [Overview](#overview)
- [What is Sources?](#what-is-sources)
- [Architecture Components](#architecture-components)
- [Sources Listener](#sources-listener)
- [Source Creation Flow](#source-creation-flow)
- [Data Ingestion Trigger](#data-ingestion-trigger)
- [Message Processing](#message-processing)
- [Source Lifecycle](#source-lifecycle)
- [Integration with Provider System](#integration-with-provider-system)
- [Monitoring and Error Handling](#monitoring-and-error-handling)

---

## Overview

The **Sources system** is Koku's integration layer with Red Hat's Platform Sources service. It enables users to configure cost management data sources (AWS, Azure, GCP, OpenShift) through a centralized platform interface, and automatically provisions those sources for data ingestion in Koku.

### Key Concepts

- **Platform Sources**: Red Hat's centralized service for managing application data sources
- **Sources Listener**: Kafka consumer that listens for source events
- **Source**: A configuration record for a cloud provider or cluster
- **Provider**: Koku's internal representation of a data source
- **Source-to-Provider Synchronization**: The process of creating/updating Koku providers from Platform Sources

---

## What is Sources?

### Platform Sources Service

Platform Sources is a Red Hat service that:
- Provides a unified interface for configuring data sources across multiple applications
- Manages authentication credentials and billing information
- Sends Kafka events when sources are created, updated, or deleted
- Allows applications (like Cost Management) to subscribe to source events

**Note for On-Premise Deployments**: For on-premise deployments without access to Red Hat SaaS services, set `KOKU_ONPREM_DEPLOYMENT=True` to disable the Unleash feature flag service. See [Feature Flags Architecture](feature-flags.md) for details on on-premise deployment configuration.

### Sources in Koku

Within Koku, **Sources** refers to:

1. **The `api_sources` database table** - Stores source configurations
2. **The Sources Listener** - Kafka consumer that processes source events
3. **The Sources Integration Service** - Synchronizes Platform Sources with Koku Providers

---

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Platform Sources Service (External)                  │
│  - User creates source via UI or API                                    │
│  - Stores authentication and billing configuration                      │
│  - Emits Kafka events                                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    Kafka Topic: platform.sources.event-stream
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Sources Listener                                │
│                  (koku/sources/kafka_listener.py)                       │
│  - Consumes Kafka messages                                              │
│  - Filters for Cost Management events                                   │
│  - Processes different event types                                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Message Processors                                   │
│             (koku/sources/kafka_message_processor.py)                   │
│  - ApplicationMsgProcessor (Application.create, update, destroy)        │
│  - AuthenticationMsgProcessor (Authentication.create, update)           │
│  - SourceMsgProcessor (Source.update)                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Sources Storage                                    │
│                    (koku/sources/storage.py)                            │
│  - Saves source details to api_sources table                            │
│  - Checks if source is ready for provider creation                      │
│  - Enqueues create/update/delete operations                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Process Queue                                       │
│               (In-memory priority queue)                                │
│  - Holds pending operations                                             │
│  - Orders by priority and timestamp                                     │
│  - Retries on failure                                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│            Sources Provider Coordinator                                 │
│        (koku/sources/sources_provider_coordinator.py)                   │
│  - Creates Koku Provider from Source                                    │
│  - Updates existing Provider                                            │
│  - Destroys Provider                                                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Provider Builder                                    │
│              (koku/api/provider/provider_builder.py)                    │
│  - Builds Provider object from Source                                   │
│  - Validates credentials and billing configuration                      │
│  - Creates tenant schema if needed                                      │
│  - Saves Provider to database                                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Provider Created                                 │
│                   (api_provider table)                                  │
│  - Provider record saved                                                │
│  - setup_complete = False (initial state)                               │
│  - polling_timestamp = None                                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Data Ingestion Begins                                 │
│         Orchestrator polls for new providers                            │
│         Downloads and processes cost/usage data                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Sources Listener

### Overview

The **Sources Listener** is a Kafka consumer that runs as a management command and listens for source events from Platform Sources.

**Location**: `koku/sources/management/commands/sources_listener.py`

**Start Command**:
```bash
python manage.py sources_listener
```

### Kafka Topics

The listener subscribes to:
- **Topic**: `platform.sources.event-stream`
- **Consumer Group**: `hccm-sources`

### Event Types

The listener processes the following Kafka event types:

#### Application Events
- `Application.create` - New application (Cost Management) added to a source
- `Application.update` - Application settings updated
- `Application.destroy` - Application removed from source
- `Application.pause` - Application paused
- `Application.unpause` - Application resumed

#### Authentication Events
- `Authentication.create` - New authentication credentials added
- `Authentication.update` - Authentication credentials updated

#### Source Events
- `Source.update` - Source name or configuration updated
- ~~`Source.destroy`~~ - Handled via Application.destroy

### Main Loop

The main message processing loop is implemented in [`listen_for_messages_loop()`](../../koku/sources/kafka_listener.py) which:
- Configures Kafka consumer with group ID `hccm-sources`
- Subscribes to the sources event stream topic
- Continuously polls for messages
- Processes each message via `listen_for_messages()`
- Executes any queued provider operations via `execute_process_queue()`

### Message Filtering

Not all messages are for Cost Management. The listener filters messages by:

1. **Application Type ID**: Only processes messages for Cost Management application
2. **Event Type**: Only processes supported event types
3. **Authentication Type**: Only processes valid authentication types

The [`msg_for_cost_mgmt()`](../../koku/sources/kafka_message_processor.py) method implements this filtering logic by checking the application type ID, validating authentication types, and verifying the message is for the Cost Management application.

---

## Source Creation Flow

### Step-by-Step Process

#### 1. User Creates Source in Platform

User creates a source through:
- Console.redhat.com UI
- Platform Sources API
- Third-party integration

Platform Sources emits Kafka events:
1. `Source.create` (ignored by Koku)
2. `Application.create` (Cost Management app added to source)
3. `Authentication.create` (credentials provided)

#### 2. Kafka Message Received

```
Event: Application.create
Headers:
  - x-rh-identity: <base64 encoded identity>
  - x-rh-sources-account-number: <account>
  - x-rh-sources-org-id: <org_id>
  - event_type: Application.create

Payload:
{
  "source_id": 12345,
  "application_type_id": 2,  // Cost Management
  "id": 67890
}
```

#### 3. Message Processor Creates Source Record

[`ApplicationMsgProcessor.process()`](../../koku/sources/kafka_message_processor.py) handles the `Application.create` event by calling `storage.create_source_event()`.

This creates a record in the `api_sources` table with:
- `source_id`: Platform Sources ID
- `account_id`: Customer account
- `org_id`: Organization ID
- `auth_header`: Identity header for API calls
- `offset`: Kafka message offset

#### 4. Fetch Source Details from Platform Sources

[`save_sources_details()`](../../koku/sources/kafka_message_processor.py) retrieves additional source information from the Platform Sources REST API including:
- `name`: Source name
- `source_type`: Provider type (AWS, Azure, GCP, OCP)
- `source_uuid`: Unique identifier

The details are saved to the database via `storage.add_provider_sources_details()`.

#### 5. Save Billing Source

For AWS, Azure, GCP (not OCP), [`save_billing_source()`](../../koku/sources/kafka_message_processor.py) retrieves billing source information from Platform Sources API and saves it via `storage.add_provider_sources_billing_info()`.

Billing source examples:
- **AWS**: `{"bucket": "my-cur-bucket", "bucket_region": "us-east-1"}`
- **Azure**: `{"resource_group": "costmanagement", "storage_account": "storage123"}`
- **GCP**: `{"dataset": "billing_export", "table": "gcp_billing_export"}`

#### 6. Wait for Authentication Event

After `Application.create`, Platform Sources sends `Authentication.create`:

```
Event: Authentication.create
Payload:
{
  "id": 99999,
  "source_id": 12345,
  "authtype": "access_key_secret_key"  // or "cloud-meter-arn", etc.
}
```

[`AuthenticationMsgProcessor.process()`](../../koku/sources/kafka_message_processor.py) handles authentication events by creating source records and calling `save_source_info(auth=True)` to retrieve and store credentials.

#### 7. Save Credentials

[`save_credentials()`](../../koku/sources/kafka_message_processor.py) retrieves authentication credentials from Platform Sources API and stores them via `storage.add_provider_sources_auth_info()`.

Credential examples:
- **AWS**: `{"role_arn": "arn:aws:iam::123456789012:role/CostManagement"}`
- **Azure**: `{"client_id": "...", "client_secret": "...", "tenant_id": "...", "subscription_id": "..."}`
- **GCP**: `{"project_id": "my-project"}`
- **OCP**: `{"cluster_id": "...", "operator_token": "..."}`

#### 8. Check if Source is Ready for Provider Creation

Once all required information is collected, the [`storage_callback()`](../../koku/sources/storage.py) Django signal handler checks if the source is ready for provider creation via `storage.screen_and_build_provider_sync_create_event()`. If ready, the event is queued for processing.

Ready conditions vary by provider (see [`_aws_provider_ready_for_create()` and similar functions](../../koku/sources/storage.py)):

**AWS Requirements**:
- source_id, name, auth_header present
- billing_source (S3 bucket) configured
- authentication (Role ARN) configured
- No error status
- Not already created (koku_uuid is None)

**OCP Requirements**:
- source_id, name, auth_header present
- authentication (Cluster ID + token) configured
- No error status
- Not already created (koku_uuid is None)

#### 9. Queue for Provider Creation

When ready, the source is added to the in-memory priority queue (`PROCESS_QUEUE`) with an event containing the operation type ("create"), provider instance, and Kafka offset.

#### 10. Execute Provider Creation

[`execute_koku_provider_op()`](../../koku/sources/kafka_listener.py) creates a `SourcesProviderCoordinator` instance and calls `create_account()` to provision the Koku provider.

#### 11. Provider Builder Creates Provider

[`SourcesProviderCoordinator.create_account()`](../../koku/sources/sources_provider_coordinator.py) delegates to [`ProviderBuilder.create_provider_from_source()`](../../koku/api/provider/provider_builder.py) which:
1. Gets or creates the customer and tenant
2. Builds provider JSON from source data (name, type, authentication, billing_source)
3. Uses `ProviderSerializer` to validate and save the provider
4. Links the provider UUID back to the source record

---

## Data Ingestion Trigger

### How Provider Creation Triggers Data Ingestion

#### 1. Provider Saved to Database

When `serializer.save()` is called, a new [`Provider`](../../koku/api/provider/models.py) record is created in `api_provider` with key fields including:
- `uuid`: Generated UUID
- `type`: Provider type (AWS, Azure, GCP, OCP)
- `authentication`, `billing_source`: Foreign keys to credential tables
- `setup_complete`: False (important - indicates initial state)
- `polling_timestamp`: None (will be set by orchestrator)
- `active`: True, `paused`: False

#### 2. Orchestrator Polling

The [`Orchestrator`](../../koku/masu/processor/orchestrator.py) runs periodically (default: hourly) via the [`check_report_updates`](../../koku/masu/celery/tasks.py) Celery beat task (schedule configured in [`koku/koku/celery.py`](../../koku/koku/celery.py)).

#### 3. Get Polling Batch

[`Orchestrator.get_polling_batch()`](../../koku/masu/processor/orchestrator.py) retrieves providers that need data downloads by:
- Querying active providers (or filtering by specific UUID/type if provided)
- Updating polling timestamps
- Checking if processing is already in progress
- Skipping disabled sources or schemas
- Returning the batch of providers ready for processing

#### 4. Determine Reports to Download

[`Orchestrator.get_reports()`](../../koku/masu/processor/orchestrator.py) determines which billing months to process:
- For initial setup (`setup_complete=False`): Downloads last 2 months (configurable via `INITIAL_INGEST_NUM_MONTHS`)
- For subsequent runs: Downloads last 2 months
- Can be overridden with specific `bill_date`

#### 5. Start Manifest Processing

[`Orchestrator.start_manifest_processing()`](../../koku/masu/processor/orchestrator.py) initiates processing for a billing month by:
1. Creating a [`ReportDownloader`](../../koku/masu/external/) instance for the provider type
2. Downloading the manifest (list of report files) via `download_manifest()`
3. Recording manifest file names in the database
4. Queueing [`get_report_files`](../../koku/masu/processor/tasks.py) Celery tasks for each file (runs in parallel)
5. Using Celery chord to trigger follow-up tasks after all files complete:
   - `summarize_reports` (aggregates data)
   - `collect_hcs_report_data_from_manifest` (HCS processing)
   - `extract_subs_data_from_reports` (subscriptions data)

#### 6. Download and Process Report Files

The [`get_report_files`](../../koku/masu/processor/tasks.py) Celery task handles individual report files by:
1. Downloading the report file from the cloud provider via `_get_report_files()`
2. Converting to Parquet format via `_process_report_file()`
3. Uploading processed data to S3
4. Returning report metadata for summarization

#### 7. Summarize Data

The [`summarize_reports`](../../koku/masu/processor/tasks.py) Celery task orchestrates summarization by:
1. Deduplicating reports by provider
2. Determining date ranges for summarization
3. Queueing [`update_summary_tables`](../../koku/masu/processor/tasks.py) tasks for each time period

#### 8. Update Summary Tables

The [`update_summary_tables`](../../koku/masu/processor/tasks.py) Celery task populates summary tables by:
1. Creating a [`ReportSummaryUpdater`](../../koku/masu/processor/) instance
2. Calling `update_summary_tables()` to aggregate data into summary tables
3. Triggering OCP on cloud summarization if applicable
4. For OCP providers: queueing `update_cost_model_costs` task
5. Marking the manifest as complete via `mark_manifest_complete`

#### 9. Mark Setup Complete

After the first successful manifest processing, the provider's `setup_complete` flag is set to `True`.

This happens in the manifest completion logic when the provider is marked as having completed its first download cycle.

---

## Message Processing

### Message Processor Classes

#### ApplicationMsgProcessor

[`ApplicationMsgProcessor`](../../koku/sources/kafka_message_processor.py) handles Application lifecycle events:
- **Application.create**: Creates source record, fetches source details, saves billing source (and auth for OCP)
- **Application.update**: Updates billing source, queues provider update if needed
- **Application.pause/unpause**: Updates source pause status
- **Application.destroy**: Queues source deletion

#### AuthenticationMsgProcessor

[`AuthenticationMsgProcessor`](../../koku/sources/kafka_message_processor.py) handles Authentication events:
- **Authentication.create**: Creates source record (if needed), saves credentials
- **Authentication.update**: Updates credentials, queues provider update if needed

#### SourceMsgProcessor

[`SourceMsgProcessor`](../../koku/sources/kafka_message_processor.py) handles Source updates:
- **Source.update**: Updates source details (name, type, etc.), updates auth for OCP, queues provider update if needed

---

## Source Lifecycle

### Complete Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Source Creation                                 │
│  1. User creates source in Platform Sources                             │
│  2. Platform emits Application.create event                             │
│  3. Platform emits Authentication.create event (except OCP in app)      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Koku Receives Events                                 │
│  1. Sources Listener filters for Cost Management events                 │
│  2. Message processors save details to api_sources table                │
│  3. Storage checks if source is ready for provider creation             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Provider Creation (when ready)                         │
│  1. Process queue executes create operation                             │
│  2. Provider Builder creates Koku Provider                              │
│  3. Provider saved with setup_complete=False                            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Initial Data Ingestion                               │
│  1. Orchestrator polls for new providers                                │
│  2. Downloads last N months of cost/usage data                          │
│  3. Processes and summarizes data                                       │
│  4. Marks provider setup_complete=True                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Ongoing Operations                                   │
│  - Daily/hourly polling for new data                                    │
│  - Process updates when source settings change                          │
│  - Handle pause/unpause events                                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Source Deletion                                    │
│  1. User deletes source in Platform Sources                             │
│  2. Platform emits Application.destroy event                            │
│  3. Koku queues provider deletion                                       │
│  4. Delete task removes provider and archived data                      │
│  5. Source record removed from api_sources                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### State Transitions

#### Source States (api_sources table)

```python
# Initial state after Application.create
source_id = 12345
name = None                    # Not yet fetched
source_type = None            # Not yet fetched
authentication = {}            # Empty
billing_source = {}            # Empty (or None for OCP)
koku_uuid = None              # No provider yet
pending_update = False
pending_delete = False

# After source details fetched
name = "My AWS Account"
source_type = "AWS"
authentication = {}            # Still empty
billing_source = {}            # Still empty

# After billing source saved
billing_source = {"data_source": {"bucket": "my-cur-bucket"}}

# After authentication saved
authentication = {"credentials": {"role_arn": "arn:aws:..."}}

# Provider creation triggered
# ... provider creation in progress ...

# Provider created successfully
koku_uuid = "abc-123-def-456"  # Links to Provider.uuid

# User updates source
pending_update = True

# Update processed
pending_update = False

# User deletes source
pending_delete = True

# Deletion completed
# Record removed from database
```

#### Provider States (api_provider table)

```python
# Initial state (just created from source)
uuid = "abc-123-def-456"
setup_complete = False
polling_timestamp = None
data_updated_timestamp = None
active = True
paused = False

# After first poll
polling_timestamp = "2025-01-15 10:00:00"

# After initial data ingestion complete
setup_complete = True
data_updated_timestamp = "2025-01-15 12:30:00"

# User pauses source
paused = True

# User resumes source
paused = False

# During deletion
active = False
authentication = None
billing_source = None

# Deleted
# Record removed from database
```

---

## Integration with Provider System

### Sources Table → Provider Table Mapping

| Sources Field    | Provider Field                              | Notes                                 |
| ---------------- | ------------------------------------------- | ------------------------------------- |
| `source_id`      | -                                           | Platform Sources ID (not in Provider) |
| `source_uuid`    | `uuid`                                      | Unique identifier (if provided)       |
| `koku_uuid`      | `uuid`                                      | Links Source to Provider              |
| `name`           | `name`                                      | Display name                          |
| `source_type`    | `type`                                      | AWS, Azure, GCP, OCP                  |
| `authentication` | `authentication` → `ProviderAuthentication` | Foreign key relationship              |
| `billing_source` | `billing_source` → `ProviderBillingSource`  | Foreign key relationship              |
| `account_id`     | `customer.account_id`                       | Account identifier                    |
| `org_id`         | `customer.org_id`                           | Organization identifier               |
| `paused`         | `paused`                                    | Pause status                          |
| `pending_update` | -                                           | Update flag (Sources only)            |
| `pending_delete` | -                                           | Delete flag (Sources only)            |

### Provider Creation from Source

```python
# Source record (api_sources)
source = {
    "source_id": 12345,
    "name": "My AWS Account",
    "source_type": "AWS",
    "authentication": {
        "credentials": {
            "role_arn": "arn:aws:iam::123456789012:role/CostManagement"
        }
    },
    "billing_source": {
        "data_source": {
            "bucket": "my-cur-bucket",
            "bucket_region": "us-east-1"
        }
    },
    "koku_uuid": None  # Will be set after provider creation
}

# Transformed to Provider data
provider_data = {
    "name": "My AWS Account",
    "type": "aws",
    "authentication": {
        "credentials": {
            "role_arn": "arn:aws:iam::123456789012:role/CostManagement"
        }
    },
    "billing_source": {
        "data_source": {
            "bucket": "my-cur-bucket",
            "bucket_region": "us-east-1"
        }
    }
}

# Provider created (api_provider)
provider = {
    "uuid": "abc-123-def-456",
    "name": "My AWS Account",
    "type": "AWS",
    "authentication": <ProviderAuthentication FK>,
    "billing_source": <ProviderBillingSource FK>,
    "customer": <Customer FK>,
    "setup_complete": False,
    "active": True,
    "paused": False
}

# Source updated with provider UUID
source.koku_uuid = "abc-123-def-456"
```

---

## Monitoring and Error Handling

### Prometheus Metrics

The Sources system exposes several Prometheus metrics (defined in [`koku/sources/`](../../koku/sources/)):
- `KAFKA_CONNECTION_ERRORS_COUNTER` - Kafka connection errors
- `SOURCES_HTTP_CLIENT_ERROR_COUNTER` - Sources HTTP client errors
- `SOURCES_KAFKA_LOOP_RETRY` - Kafka loop retries
- `SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER` - Provider operation retry loop

### Error Types and Handling

#### Recoverable Errors

These errors cause the operation to be retried:

1. **IntegrityError**: Database constraint violations
2. **InterfaceError**: Database connection issues
3. **OperationalError**: Database operational issues
4. **SourcesHTTPClientError**: Temporary API failures

**Retry Strategy**: The [`_requeue_provider_sync_message()`](../../koku/sources/kafka_listener.py) helper function implements retry logic with configurable sleep duration (default: 10 seconds) and increments the retry counter metric.

#### Non-Recoverable Errors

These errors are logged but not retried:

1. **ValidationError**: Invalid provider configuration
2. **ProviderBuilderError**: Provider creation failed validation
3. **SourceNotFoundError**: Source was deleted in Platform Sources

**Error Handling**: Non-recoverable errors are logged and the error status is reported back to Platform Sources via `sources_client.set_source_status()`.

### Status Reporting

Koku reports source status back to Platform Sources via the [`set_source_status()`](../../koku/sources/sources_http_client.py) method, which sets the availability status to "available" or "unavailable" with error details when issues occur.

### Logging

Structured logging is used throughout the Sources system via the [`log_json()`](../../koku/masu/util/common.py) utility, which includes tracing IDs, source IDs, event types, and operation details for correlation and debugging.

### Process Queue Management

The in-memory [`PROCESS_QUEUE`](../../koku/sources/kafka_listener.py) (a Python `PriorityQueue`) ensures operations are executed in order:
- Events are added with sequential numbering for FIFO ordering within same priority level
- Processing loop consumes events via `process_synchronize_sources_msg()`
- **Priority**: Lower numbers = higher priority

### Recovery on Restart

When the Sources Listener starts, [`load_process_queue()`](../../koku/sources/kafka_listener.py) re-populates the process queue by:
1. Calling `_collect_pending_items()` to gather pending sources from the database
2. Loading sources ready for creation (koku_uuid=None and ready)
3. Loading sources marked for update (pending_update=True)
4. Loading sources marked for deletion (pending_delete=True)
5. Re-queuing all pending operations

This ensures that if the Sources Listener crashes or is restarted, pending operations are not lost.

---

## Summary

### Key Takeaways

1. **Sources is the Integration Layer**: It connects Platform Sources with Koku's Provider system
2. **Event-Driven Architecture**: Uses Kafka for asynchronous, reliable message delivery
3. **Multi-Step Process**: Source creation involves multiple Kafka events and REST API calls
4. **Validation and Readiness**: Sources are only promoted to Providers when all required configuration is present
5. **Automatic Data Ingestion**: Once a Provider is created, the Orchestrator automatically begins downloading data
6. **Error Recovery**: Retry mechanisms and persistent queue ensure reliable operation
7. **Two-Way Communication**: Koku reports source status back to Platform Sources

### Data Flow Summary

```
Platform Sources (User Action)
  → Kafka Events (Application.create, Authentication.create)
    → Sources Listener (Kafka Consumer)
      → Message Processors (Save to api_sources)
        → Storage Validation (Check if ready)
          → Process Queue (Pending operations)
            → Provider Coordinator (Create provider)
              → Provider Builder (Save to api_provider)
                → Orchestrator (Poll for new providers)
                  → Data Ingestion (Download, process, summarize)
```

---

## Related Documentation

- [Celery Tasks Architecture](./celery-tasks.md)
- [API Serializers and Provider Maps](./api-serializers-provider-maps.md)
- [Data Processing Patterns](./.cursor/rules/data-processing.mdc)
- [Provider Models](../../koku/api/provider/models.py)
- [Sources Storage](../../koku/sources/storage.py)

---

## Document Version

- **Last Updated**: 2025-10-21
- **Koku Version**: Current
- **Author**: Architecture Documentation
