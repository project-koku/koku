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

### Sources in Koku

Within Koku, **Sources** refers to:

1. **The `api_sources` database table** - Stores source configurations
2. **The Sources Listener** - Kafka consumer that processes source events
3. **The Sources Integration Service** - Synchronizes Platform Sources with Koku Providers

---

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Platform Sources Service (External)                   │
│  - User creates source via UI or API                                    │
│  - Stores authentication and billing configuration                       │
│  - Emits Kafka events                                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    Kafka Topic: platform.sources.event-stream
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Sources Listener                                 │
│                  (koku/sources/kafka_listener.py)                       │
│  - Consumes Kafka messages                                              │
│  - Filters for Cost Management events                                   │
│  - Processes different event types                                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Message Processors                                    │
│             (koku/sources/kafka_message_processor.py)                   │
│  - ApplicationMsgProcessor (Application.create, update, destroy)        │
│  - AuthenticationMsgProcessor (Authentication.create, update)           │
│  - SourceMsgProcessor (Source.update)                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Sources Storage                                     │
│                    (koku/sources/storage.py)                            │
│  - Saves source details to api_sources table                            │
│  - Checks if source is ready for provider creation                      │
│  - Enqueues create/update/delete operations                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Process Queue                                        │
│               (In-memory priority queue)                                 │
│  - Holds pending operations                                             │
│  - Orders by priority and timestamp                                     │
│  - Retries on failure                                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│            Sources Provider Coordinator                                  │
│        (koku/sources/sources_provider_coordinator.py)                   │
│  - Creates Koku Provider from Source                                    │
│  - Updates existing Provider                                            │
│  - Destroys Provider                                                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Provider Builder                                     │
│              (koku/api/provider/provider_builder.py)                    │
│  - Builds Provider object from Source                                   │
│  - Validates credentials and billing configuration                      │
│  - Creates tenant schema if needed                                      │
│  - Saves Provider to database                                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Provider Created                                  │
│                   (api_provider table)                                   │
│  - Provider record saved                                                │
│  - setup_complete = False (initial state)                               │
│  - polling_timestamp = None                                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Data Ingestion Begins                                  │
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

```python
def listen_for_messages_loop(application_source_id):
    """Continuously listen for Kafka messages."""
    kafka_conf = {
        "group.id": "hccm-sources",
        "queued.max.messages.kbytes": 1024,
        "enable.auto.commit": False,
    }
    consumer = get_consumer(kafka_conf)
    consumer.subscribe([SOURCES_TOPIC])

    LOG.info("Listener started. Waiting for messages...")

    while True:
        msg_list = consumer.consume()
        if len(msg_list) == 1:
            msg = msg_list.pop()
        else:
            consumer.commit()
            continue

        # Process the message
        listen_for_messages(msg, consumer, application_source_id)

        # Execute any queued operations
        execute_process_queue()
```

### Message Filtering

Not all messages are for Cost Management. The listener filters messages by:

1. **Application Type ID**: Only processes messages for Cost Management application
2. **Event Type**: Only processes supported event types
3. **Authentication Type**: Only processes valid authentication types

```python
def msg_for_cost_mgmt(self):
    """Filter messages not intended for cost management."""
    if self.event_type in (APPLICATION_CREATE, APPLICATION_UPDATE, ...):
        return self.application_type_id == self.cost_mgmt_id

    if self.event_type in (AUTHENTICATION_CREATE, AUTHENTICATION_UPDATE):
        if self.value.get("authtype") not in AUTH_TYPES.values():
            return False
        sources_network = self.get_sources_client()
        return sources_network.get_application_type_is_cost_management(self.cost_mgmt_id)

    return self.event_type in (SOURCE_UPDATE,)
```

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

`ApplicationMsgProcessor.process()` handles the `Application.create` event:

```python
def process(self):
    if self.event_type in (KAFKA_APPLICATION_CREATE,):
        LOG.debug(f"creating source for source_id: {self.source_id}")

        # Create initial source record
        storage.create_source_event(
            self.source_id,
            self.account_number,
            self.org_id,
            self.auth_header,
            self.offset
        )
```

This creates a record in the `api_sources` table with:
- `source_id`: Platform Sources ID
- `account_id`: Customer account
- `org_id`: Organization ID
- `auth_header`: Identity header for API calls
- `offset`: Kafka message offset

#### 4. Fetch Source Details from Platform Sources

```python
def save_sources_details(self):
    """Get additional sources context from Sources REST API."""
    LOG.info(f"starting for source_id {self.source_id}")

    details = self.get_source_details()
    # Details include:
    #  - name: Source name
    #  - source_type: Provider type (AWS, Azure, GCP, OCP)
    #  - source_uuid: Unique identifier

    if not details.source_type:
        LOG.warning(f"unexpected source_type_id: {details.source_type_id}")
        return

    result = storage.add_provider_sources_details(details, self.source_id)
    LOG.info(f"complete for source_id {self.source_id}: {result}")
    return result
```

#### 5. Save Billing Source

For AWS, Azure, GCP (not OCP):

```python
def save_billing_source(self):
    """Store Sources billing information."""
    LOG.info(f"starting for source_id {self.source_id}")

    source_type = storage.get_source_type(self.source_id)

    if source_type == Provider.PROVIDER_OCP:
        LOG.info("skipping for OCP source")
        return

    sources_network = self.get_sources_client()

    try:
        data_source = {"data_source": sources_network.get_data_source(source_type, self.cost_mgmt_id)}
    except SourcesHTTPClientError as error:
        LOG.info(f"billing info not available for source_id: {self.source_id}")
        sources_network.set_source_status(error)
        raise error

    if not data_source.get("data_source"):
        return

    result = bool(storage.add_provider_sources_billing_info(self.source_id, data_source))
    LOG.info(f"completed for source_id: {self.source_id}: {result}")
    return result
```

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

`AuthenticationMsgProcessor.process()` handles it:

```python
def process(self):
    if self.event_type in (KAFKA_AUTHENTICATION_CREATE):
        LOG.debug(f"creating source for source_id: {self.source_id}")
        storage.create_source_event(...)

    if storage.is_known_source(self.source_id):
        if self.event_type in (KAFKA_AUTHENTICATION_CREATE):
            self.save_source_info(auth=True)
```

#### 7. Save Credentials

```python
def save_credentials(self):
    """Store Sources Authentication information."""
    LOG.info(f"starting for source_id {self.source_id}")

    source_type = storage.get_source_type(self.source_id)
    sources_network = self.get_sources_client()

    try:
        authentication = {"credentials": sources_network.get_credentials(source_type, self.cost_mgmt_id)}
    except SourcesHTTPClientError as error:
        LOG.info(f"authentication info not available for source_id: {self.source_id}")
        sources_network.set_source_status(error)
        raise error

    if not authentication.get("credentials"):
        return

    result = bool(storage.add_provider_sources_auth_info(self.source_id, authentication))
    LOG.info(f"complete for source_id: {self.source_id}: {result}")
    return result
```

Credential examples:
- **AWS**: `{"role_arn": "arn:aws:iam::123456789012:role/CostManagement"}`
- **Azure**: `{"client_id": "...", "client_secret": "...", "tenant_id": "...", "subscription_id": "..."}`
- **GCP**: `{"project_id": "my-project"}`
- **OCP**: `{"cluster_id": "...", "operator_token": "..."}`

#### 8. Check if Source is Ready for Provider Creation

Once all required information is collected, the storage callback checks:

```python
@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""

    # Check if ready for creation
    process_event = storage.screen_and_build_provider_sync_create_event(instance)
    if process_event:
        _log_process_queue_event(PROCESS_QUEUE, process_event, "storage_callback")
        LOG.debug(f"Create Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), process_event))

    execute_process_queue()
```

Ready conditions vary by provider:

**AWS Requirements**:
```python
def _aws_provider_ready_for_create(provider):
    return bool(
        provider.source_id
        and provider.name
        and provider.auth_header
        and provider.billing_source  # S3 bucket
        and provider.authentication  # Role ARN
        and not provider.status  # No errors
        and not provider.koku_uuid  # Not already created
    )
```

**OCP Requirements**:
```python
def _ocp_provider_ready_for_create(provider):
    return bool(
        provider.source_id
        and provider.name
        and provider.authentication  # Cluster ID + token
        and provider.auth_header
        and not provider.status
        and not provider.koku_uuid
    )
```

#### 9. Queue for Provider Creation

When ready, the source is added to the process queue:

```python
process_event = {
    "operation": "create",
    "provider": source_instance,
    "offset": kafka_offset
}

PROCESS_QUEUE.put_nowait((priority, process_event))
```

#### 10. Execute Provider Creation

```python
def execute_koku_provider_op(msg):
    """Execute the 'create' or 'destroy' Koku-Provider operations."""
    provider: Sources = msg.get("provider")
    operation = msg.get("operation")

    account_coordinator = SourcesProviderCoordinator(
        provider.source_id,
        provider.auth_header,
        provider.account_id,
        provider.org_id
    )

    if operation == "create":
        LOG.info(f"creating Koku Provider for source_id: {provider.source_id}")
        instance = account_coordinator.create_account(provider)
        LOG.info(f"created provider {instance.uuid} for source_id: {provider.source_id}")
```

#### 11. Provider Builder Creates Provider

```python
def create_account(self, source):
    """Call to create provider."""
    try:
        LOG.info(f"Creating Provider for Source ID: {str(self._source_id)}")
        provider = self._provider_builder.create_provider_from_source(source)
        add_provider_koku_uuid(self._source_id, provider.uuid)
    except ProviderBuilderError as provider_err:
        raise SourcesProviderCoordinatorError(str(provider_err))
    return provider
```

```python
def create_provider_from_source(self, source):
    """Call to create provider."""
    connection.set_schema_to_public()

    # Get or create customer and tenant
    context, customer, _ = self._create_context()
    tenant = self._tenant_for_schema(customer.schema_name)

    # Build provider JSON
    provider_type = source.source_type
    json_data = {
        "name": source.name,
        "type": provider_type.lower(),
        "authentication": self._build_credentials_auth(provider_type, source.authentication),
        "billing_source": self.get_billing_source_for_provider(provider_type, source.billing_source),
    }
    if source.source_uuid:
        json_data["uuid"] = str(source.source_uuid)

    # Create provider
    connection.set_tenant(tenant)
    serializer = ProviderSerializer(data=json_data, context=context)

    try:
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()  # <-- Provider created here
    finally:
        invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)
        connection.set_schema_to_public()

    return instance
```

---

## Data Ingestion Trigger

### How Provider Creation Triggers Data Ingestion

#### 1. Provider Saved to Database

When `serializer.save()` is called, a new `Provider` record is created in `api_provider`:

```python
# Provider fields at creation:
uuid = <generated UUID>
name = "My AWS Account"
type = "AWS"
authentication = <foreign key to ProviderAuthentication>
billing_source = <foreign key to ProviderBillingSource>
customer = <foreign key to Customer>
setup_complete = False        # Important!
created_timestamp = <now>
polling_timestamp = None      # Will be set by orchestrator
data_updated_timestamp = None
active = True
paused = False
```

#### 2. Orchestrator Polling

The `Orchestrator` runs periodically (default: hourly) via Celery beat task:

```python
# Celery beat schedule (koku/koku/celery.py)
CHECK_REPORT_UPDATES_DEF = {
    "task": "masu.celery.tasks.check_report_updates",
    "schedule": crontab(*REPORT_DOWNLOAD_SCHEDULE.split(" ", 5)),  # Default: "0 * * * *"
    "kwargs": {},
}
```

#### 3. Get Polling Batch

```python
def get_polling_batch(self):
    """Get providers that need to be polled."""
    if self.provider_uuid:
        providers = Provider.objects.filter(uuid=self.provider_uuid)
    else:
        filters = {}
        if self.provider_type:
            filters["type"] = self.provider_type
        providers = Provider.polling_objects.get_polling_batch(filters=filters)

    batch = []
    for provider in providers:
        schema_name = provider.account.get("schema_name")

        # Check if currently processing
        if check_currently_processing(schema_name, provider):
            LOG.info(f"processing currently in progress for provider {provider.uuid}")
            provider.polling_timestamp = self.dh.now_utc
            provider.save(update_fields=["polling_timestamp"])
            continue

        # Update polling timestamp
        provider.polling_timestamp = self.dh.now_utc
        provider.save(update_fields=["polling_timestamp"])

        # Check if source/processing is disabled
        if is_cloud_source_processing_disabled(schema_name):
            LOG.info(f"processing disabled for schema {schema_name}")
            continue

        if is_source_disabled(provider.uuid):
            LOG.info(f"processing disabled for source {provider.uuid}")
            continue

        batch.append(provider)

    return batch
```

#### 4. Determine Reports to Download

```python
def get_reports(self, provider_uuid):
    """Get months for provider to process."""
    if self.bill_date:
        return [get_billing_month_start(self.bill_date)]

    # Check if initial setup is complete
    if Config.INGEST_OVERRIDE or not check_provider_setup_complete(provider_uuid):
        number_of_months = Config.INITIAL_INGEST_NUM_MONTHS  # Default: 2
    else:
        number_of_months = 2

    return get_billing_months(number_of_months)
```

**Initial Ingest**: Downloads last 2 months of data (configurable via `INITIAL_INGEST_NUM_MONTHS`)

#### 5. Start Manifest Processing

For each billing month:

```python
def start_manifest_processing(
    self,
    customer_name,
    credentials,
    data_source,
    provider_type,
    schema_name,
    provider_uuid,
    report_month,
    **kwargs
):
    """Start processing an account's manifest for the specified report_month."""

    # Create downloader
    downloader = ReportDownloader(
        customer_name=customer_name,
        credentials=credentials,
        data_source=data_source,
        provider_type=provider_type,
        provider_uuid=provider_uuid,
        report_name=None,
    )

    # Download manifest (list of files)
    manifest_list = downloader.download_manifest(report_month)

    report_tasks = []
    for manifest in manifest_list:
        tracing_id = manifest.get("assembly_id", "no-request-id")
        report_files = manifest.get("files", [])

        # Save manifest file names
        record_all_manifest_files(
            manifest["manifest_id"],
            [report.get("local_file") for report in manifest.get("files", [])],
            tracing_id,
        )

        # Queue download tasks for each file
        for report_file_dict in report_files:
            report_context = manifest.copy()
            report_context["current_file"] = report_file_dict.get("key")
            report_context["request_id"] = tracing_id

            report_tasks.append(
                get_report_files.s(
                    customer_name,
                    credentials,
                    data_source,
                    provider_type,
                    schema_name,
                    provider_uuid,
                    report_month,
                    report_context,
                    tracing_id=tracing_id,
                ).set(queue=REPORT_QUEUE)
            )

    # Execute download tasks in parallel with summary chained
    if report_tasks:
        hcs_task = collect_hcs_report_data_from_manifest.s().set(queue=HCS_Q)
        summary_task = summarize_reports.s(manifest_list=manifest_list).set(queue=SUMMARY_QUEUE)
        subs_task = extract_subs_data_from_reports.s().set(queue=SUBS_EXTRACTION_QUEUE)

        async_id = chord(report_tasks, group(summary_task, hcs_task, subs_task))()
        LOG.info(f"Manifest Processing Async ID: {async_id}")

    return manifest_list, reports_tasks_queued
```

#### 6. Download and Process Report Files

Each file is processed by the `get_report_files` Celery task:

```python
@celery_app.task(name="masu.processor.tasks.get_report_files", queue=DownloadQueue.DEFAULT)
def get_report_files(
    customer_name,
    authentication,
    billing_source,
    provider_type,
    schema_name,
    provider_uuid,
    report_month,
    report_context,
    tracing_id,
    **kwargs
):
    """Task to download a Report and process the report."""

    # Download report file from cloud provider
    report_dict = _get_report_files(
        tracing_id,
        customer_name,
        authentication,
        billing_source,
        provider_type,
        provider_uuid,
        month,
        report_context,
    )

    # Convert to Parquet and upload to S3
    result = _process_report_file(
        schema_name,
        provider_type,
        report_dict,
    )

    return report_meta
```

#### 7. Summarize Data

After all files are processed, the `summarize_reports` task runs:

```python
@celery_app.task(name="masu.processor.tasks.summarize_reports", queue=SummaryQueue.DEFAULT)
def summarize_reports(reports_to_summarize, **kwargs):
    """Summarize reports returned from line summary task."""

    reports_deduplicated = deduplicate_summary_reports(reports_to_summarize)

    for report in reports_deduplicated:
        schema_name = report.get("schema_name")

        months = get_months_in_date_range(
            start=report.get("start"),
            end=report.get("end"),
            report=True,
        )

        for month in months:
            # Queue summary table update
            update_summary_tables.s(
                schema_name,
                report.get("provider_type"),
                report.get("provider_uuid"),
                start_date=month[0],
                end_date=month[1],
                manifest_id=report.get("manifest_id"),
                tracing_id=tracing_id,
            ).apply_async(queue=fallback_queue)
```

#### 8. Update Summary Tables

```python
@celery_app.task(name="masu.processor.tasks.update_summary_tables", queue=SummaryQueue.DEFAULT)
def update_summary_tables(
    schema,
    provider_type,
    provider_uuid,
    start_date,
    end_date=None,
    manifest_id=None,
    **kwargs
):
    """Populate the summary tables for reporting."""

    # Update summary tables
    updater = ReportSummaryUpdater(schema, provider_uuid, manifest_id, tracing_id)
    start_date, end_date = updater.update_summary_tables(start_date, end_date, tracing_id)

    # Trigger OCP on cloud if applicable
    trigger_ocp_on_cloud_summary(...)

    # Update cost model costs (for OCP)
    if provider_type == Provider.PROVIDER_OCP:
        update_cost_model_costs.s(...).apply_async()

    # Mark manifest complete
    mark_manifest_complete.s(...).apply_async()
```

#### 9. Mark Setup Complete

After the first successful manifest processing, the provider's `setup_complete` flag is set to `True`.

This happens in the manifest completion logic when the provider is marked as having completed its first download cycle.

---

## Message Processing

### Message Processor Classes

#### ApplicationMsgProcessor

Handles Application lifecycle events:

```python
class ApplicationMsgProcessor(KafkaMessageProcessor):
    def process(self):
        if self.event_type in (KAFKA_APPLICATION_CREATE,):
            # Create source record
            storage.create_source_event(...)
            # Fetch and save source details
            self.save_sources_details()
            # Save billing source
            self.save_source_info(bill=True)
            # For OCP, also save auth (no separate auth message)
            if storage.get_source_type(self.source_id) == Provider.PROVIDER_OCP:
                self.save_source_info(auth=True)

        if self.event_type in (KAFKA_APPLICATION_UPDATE,):
            updated = self.save_source_info(bill=True)
            if updated:
                storage.enqueue_source_create_or_update(self.source_id)

        if self.event_type in (KAFKA_APPLICATION_PAUSE, KAFKA_APPLICATION_UNPAUSE):
            pause = self.event_type == KAFKA_APPLICATION_PAUSE
            storage.add_source_pause(self.source_id, pause)

        if self.event_type in (KAFKA_APPLICATION_DESTROY,):
            storage.enqueue_source_delete(self.source_id, self.offset)
```

#### AuthenticationMsgProcessor

Handles Authentication events:

```python
class AuthenticationMsgProcessor(KafkaMessageProcessor):
    def process(self):
        if self.event_type in (KAFKA_AUTHENTICATION_CREATE):
            # Create source record if doesn't exist
            storage.create_source_event(...)
            # Save credentials
            self.save_source_info(auth=True)

        if self.event_type in (KAFKA_AUTHENTICATION_UPDATE):
            updated = self.save_source_info(auth=True)
            if updated:
                storage.enqueue_source_create_or_update(self.source_id)
```

#### SourceMsgProcessor

Handles Source updates:

```python
class SourceMsgProcessor(KafkaMessageProcessor):
    def process(self):
        if not storage.is_known_source(self.source_id):
            LOG.info("update event for unknown source_id, skipping...")
            return

        # Update source details (name, type, etc.)
        updated = self.save_sources_details()

        # For OCP, also update auth
        if storage.get_source_type(self.source_id) == Provider.PROVIDER_OCP:
            updated |= self.save_source_info(auth=True)

        if updated:
            storage.enqueue_source_create_or_update(self.source_id)
```

---

## Source Lifecycle

### Complete Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Source Creation                                  │
│  1. User creates source in Platform Sources                            │
│  2. Platform emits Application.create event                             │
│  3. Platform emits Authentication.create event (except OCP in app)     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Koku Receives Events                                  │
│  1. Sources Listener filters for Cost Management events                │
│  2. Message processors save details to api_sources table               │
│  3. Storage checks if source is ready for provider creation            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Provider Creation (when ready)                          │
│  1. Process queue executes create operation                             │
│  2. Provider Builder creates Koku Provider                              │
│  3. Provider saved with setup_complete=False                            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Initial Data Ingestion                                │
│  1. Orchestrator polls for new providers                                │
│  2. Downloads last N months of cost/usage data                          │
│  3. Processes and summarizes data                                       │
│  4. Marks provider setup_complete=True                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Ongoing Operations                                    │
│  - Daily/hourly polling for new data                                    │
│  - Process updates when source settings change                          │
│  - Handle pause/unpause events                                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Source Deletion                                     │
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

The Sources system exposes several Prometheus metrics:

```python
# Kafka connection errors
KAFKA_CONNECTION_ERRORS_COUNTER

# Sources HTTP client errors
SOURCES_HTTP_CLIENT_ERROR_COUNTER

# Kafka loop retries
SOURCES_KAFKA_LOOP_RETRY

# Provider operation retry loop
SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER
```

### Error Types and Handling

#### Recoverable Errors

These errors cause the operation to be retried:

1. **IntegrityError**: Database constraint violations
2. **InterfaceError**: Database connection issues
3. **OperationalError**: Database operational issues
4. **SourcesHTTPClientError**: Temporary API failures

**Retry Strategy**:
```python
def _requeue_provider_sync_message(priority, msg, queue):
    """Helper to requeue provider sync messages."""
    SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER.inc()
    time.sleep(Config.RETRY_SECONDS)  # Default: 10 seconds
    queue.put((priority, msg))
    LOG.warning(f'Requeue of failed operation: {msg.get("operation")}')
```

#### Non-Recoverable Errors

These errors are logged but not retried:

1. **ValidationError**: Invalid provider configuration
2. **ProviderBuilderError**: Provider creation failed validation
3. **SourceNotFoundError**: Source was deleted in Platform Sources

**Error Handling**:
```python
try:
    execute_koku_provider_op(msg)
except ValidationError as account_error:
    LOG.warning(f"unable to {operation} provider: {account_error}")
    sources_client.set_source_status(account_error)  # Update Platform Sources
```

### Status Reporting

Koku reports source status back to Platform Sources:

```python
def set_source_status(self, error):
    """Set source status in Platform Sources."""
    if error:
        status_obj = {
            "availability_status": "unavailable",
            "availability_status_error": str(error)
        }
    else:
        status_obj = {
            "availability_status": "available"
        }

    try:
        response = self._send_post_request(
            url=f"/api/sources/v3.1/applications/{app_id}",
            data=status_obj
        )
    except SourcesHTTPClientError as error:
        LOG.error(f"Unable to set source status: {error}")
```

### Logging

Structured logging is used throughout:

```python
LOG.info(
    log_json(
        tracing_id,
        msg="processing cost-mgmt message",
        source_id=source_id,
        event_type=event_type,
        operation=operation
    )
)
```

### Process Queue Management

The in-memory process queue ensures operations are executed in order:

```python
PROCESS_QUEUE = queue.PriorityQueue()
COUNT = itertools.count()  # Sequential numbering

# Add to queue with priority
PROCESS_QUEUE.put_nowait((next(COUNT), event))

# Process queue
while not PROCESS_QUEUE.empty():
    priority, msg = PROCESS_QUEUE.get()
    process_synchronize_sources_msg((priority, msg), PROCESS_QUEUE)
```

**Priority**: Lower numbers = higher priority. Uses sequential count for FIFO within same priority level.

### Recovery on Restart

When the Sources Listener starts, it reloads pending operations:

```python
def load_process_queue():
    """Re-populate the process queue for any Source events that need synchronization."""
    pending_events = _collect_pending_items()
    for event in pending_events:
        PROCESS_QUEUE.put_nowait((next(COUNT), event))

def _collect_pending_items():
    """Gather all sources to create, update, or delete."""
    create_events = storage.load_providers_to_create()    # koku_uuid=None and ready
    update_events = storage.load_providers_to_update()    # pending_update=True
    destroy_events = storage.load_providers_to_delete()   # pending_delete=True
    return create_events + update_events + destroy_events
```

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
