# Celery Tasks Architecture

This document provides a comprehensive map of all Celery tasks used in the Koku project. Tasks are organized by their module and purpose.

## Table of Contents

- [Report Processing Tasks](#report-processing-tasks)
- [Data Management Tasks](#data-management-tasks)
- [Provider Management Tasks](#provider-management-tasks)
- [Cost Model Tasks](#cost-model-tasks)
- [HCS (Hybrid Committed Spend) Tasks](#hcs-hybrid-committed-spend-tasks)
- [Subscriptions (SUBS) Tasks](#subscriptions-subs-tasks)
- [Sources Tasks](#sources-tasks)
- [Scheduled Beat Tasks](#scheduled-beat-tasks)
- [Queue Configuration](#queue-configuration)

---

## Report Processing Tasks

### `masu.processor.tasks.get_report_files`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `DownloadQueue.DEFAULT`

**Description**: Downloads and processes individual report files from cloud providers. This is the primary task for report ingestion.

**Key Parameters**:
- `customer_name` - Name of the customer owning the cost usage report
- `authentication` - Credentials for accessing the report
- `billing_source` - Location of the cost usage report
- `provider_type` - Provider type (AWS, Azure, GCP, OCP)
- `schema_name` - Database schema name
- `provider_uuid` - Provider unique identifier
- `report_month` - Month for report processing
- `report_context` - Context information including manifest_id, file keys
- `tracing_id` - Request tracing identifier
- `ingress_reports` - Optional ingress report data
- `ingress_reports_uuid` - Optional ingress report UUID

**Retry Configuration**:
- Auto-retries on `TrinoQueryNotFoundError`
- Max retries: Configured via `settings.MAX_UPDATE_RETRIES`
- Exponential backoff with jitter (max 600 seconds)

**Workflow**:
1. Downloads report file from provider
2. Extracts and processes the report file (converts to Parquet)
3. Pushes processed data to S3
4. Returns report metadata for summarization

---

### `masu.processor.tasks.summarize_reports`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Description**: Orchestrates the summarization of processed reports. Deduplicates reports and triggers summary table updates.

**Key Parameters**:
- `reports_to_summarize` - List of reports to process
- `queue_name` - Optional queue override
- `manifest_list` - List of manifest IDs
- `ingress_report_uuid` - Optional ingress report UUID

**Workflow**:
1. Deduplicates reports by provider
2. Determines date ranges for summarization
3. Triggers `update_summary_tables` for each time period

---

### `masu.processor.tasks.update_summary_tables`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Task Name**: `masu.processor.tasks.update_summary_tables`

**Description**: Populates summary tables with aggregated cost and usage data. This is the core summarization task.

**Key Parameters**:
- `schema` - Database schema name
- `provider_type` - Provider type
- `provider_uuid` - Provider unique identifier
- `start_date` - Start date for summarization
- `end_date` - End date for summarization (optional)
- `manifest_id` - Manifest identifier
- `ingress_report_uuid` - Ingress report UUID (optional)
- `queue_name` - Queue override (optional)
- `synchronous` - Run synchronously flag (default: False)
- `tracing_id` - Tracing identifier
- `ocp_on_cloud` - Enable OCP on cloud processing (default: True)
- `manifest_list` - List of manifests
- `invoice_month` - Invoice month for processing

**Workflow**:
1. Checks if task is already running or rate-limited
2. Calls `ReportSummaryUpdater` to aggregate data into summary tables
3. Triggers OCP on cloud summarization if applicable
4. For OCP providers: triggers cost model updates
5. Marks manifest as complete
6. Triggers data validation

**Dependencies**:
- Chains to `update_cost_model_costs` (for OCP)
- Chains to `mark_manifest_complete`
- Chains to `validate_daily_data`

---

### `masu.processor.tasks.update_all_summary_tables`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Description**: Triggers summary table updates for all providers across all schemas. Used for bulk re-summarization operations.

**Key Parameters**:
- `start_date` - Start date for summarization
- `end_date` - End date for summarization (optional)

**Workflow**:
1. Retrieves all active provider accounts
2. Queues `update_summary_tables` for each provider

---

### `masu.processor.tasks.update_openshift_on_cloud`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Description**: Updates OpenShift on Cloud summary data by correlating OCP usage with infrastructure provider costs.

**Key Parameters**:
- `schema_name` - Database schema
- `openshift_provider_uuid` - OpenShift provider UUID
- `infrastructure_provider_uuid` - Infrastructure provider UUID (AWS/Azure/GCP)
- `infrastructure_provider_type` - Infrastructure provider type
- `start_date` - Start date
- `end_date` - End date
- `manifest_id` - Manifest ID (optional)
- `queue_name` - Queue override (optional)
- `synchronous` - Synchronous execution flag
- `tracing_id` - Tracing ID

**Retry Configuration**:
- Auto-retries on `ReportSummaryUpdaterCloudError`
- Max retries: `settings.MAX_UPDATE_RETRIES`

**Workflow**:
1. Retrieves latest OCP manifest
2. Checks rate limiting and task deduplication
3. Updates OCP on cloud summary tables
4. Triggers cost model updates
5. Triggers data validation

---

### `masu.processor.tasks.delete_openshift_on_cloud_data`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `RefreshQueue.DEFAULT`

**Description**: Deletes or truncates OCP on cloud summary data for a specific date range and table.

**Key Parameters**:
- `schema_name` - Database schema
- `infrastructure_provider_uuid` - Infrastructure provider UUID
- `start_date` - Start date
- `end_date` - End date
- `table_name` - Table to delete from
- `operation` - Operation type (DELETE_TABLE or TRUNCATE_TABLE)
- `manifest_id` - Manifest ID (optional)
- `tracing_id` - Tracing ID

---

## Data Management Tasks

### `masu.processor.tasks.remove_expired_data`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `DEFAULT`

**Description**: Removes expired report data based on retention policies.

**Key Parameters**:
- `schema_name` - Database schema
- `provider` - Provider type
- `simulate` - Simulation mode (no actual deletion)
- `provider_uuid` - Provider UUID (optional)
- `queue_name` - Queue override (optional)

---

### `masu.processor.tasks.remove_expired_trino_partitions`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `DEFAULT`

**Description**: Removes expired Trino/Hive partitions from object storage.

**Key Parameters**:
- `schema_name` - Database schema
- `provider_type` - Provider type
- `simulate` - Simulation mode

---

### `masu.celery.tasks.remove_expired_data`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Scheduled task that initiates removal of expired report data and Trino partitions for all providers.

**Key Parameters**:
- `simulate` - Simulation mode (default: False)

**Workflow**:
1. Creates an Orchestrator instance
2. Calls `remove_expired_report_data()` for all accounts
3. Calls `remove_expired_trino_partitions()` for OCP providers

---

### `masu.celery.tasks.delete_archived_data`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Description**: Deletes archived data from S3 for a deleted provider. Uses exponential backoff retry strategy.

**Key Parameters**:
- `schema_name` - Database schema
- `provider_type` - Provider type
- `provider_uuid` - Provider UUID

**Retry Configuration**:
- Auto-retries on `ClientError` (AWS)
- Max retries: 10
- Retry backoff: 10 seconds (exponential)

**Workflow**:
1. Validates input parameters
2. Constructs S3 prefixes for CSV and Parquet data
3. Deletes S3 objects under those prefixes
4. For OCP: deletes Hive/Trino partitions

---

### `masu.celery.tasks.purge_trino_files`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Removes files from S3 with a specific prefix. Used for data purging operations.

**Key Parameters**:
- `prefix` - S3 prefix path
- `schema_name` - Database schema
- `provider_type` - Provider type
- `provider_uuid` - Provider UUID

**Feature Flag**: Requires `enable-purge-turnpikes` Unleash flag

---

### `masu.celery.tasks.purge_manifest_records`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Removes manifest records from the database for a provider and date range.

**Key Parameters**:
- `schema_name` - Database schema
- `provider_uuid` - Provider UUID
- `dates` - Dictionary with either `start_date`/`end_date` or `bill_date`

**Feature Flag**: Requires `enable-purge-turnpikes` Unleash flag

**Side Effects**:
- Sets provider `setup_complete` to `False`

---

### `masu.processor.tasks.autovacuum_tune_schema`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `DEFAULT`

**Description**: Tunes PostgreSQL autovacuum settings for tables based on their size.

**Key Parameters**:
- `schema_name` - Database schema to tune

**Configuration**:
- Uses `AUTOVACUUM_TUNING` environment variable for custom thresholds
- Default scale factors:
  - 10M+ rows: 0.01
  - 1M+ rows: 0.02
  - 100K+ rows: 0.05

**Workflow**:
1. Queries table statistics (n_live_tup)
2. Determines appropriate autovacuum_vacuum_scale_factor
3. Adjusts table-level PostgreSQL settings

---

### `masu.celery.tasks.autovacuum_tune_schemas`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Scheduled task that triggers autovacuum tuning for all tenant schemas.

**Workflow**:
1. Retrieves all tenant schemas
2. Queues `autovacuum_tune_schema` for each schema

---

### `masu.processor.tasks.remove_stale_tenants`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `DEFAULT`

**Description**: Removes stale tenant records that have no associated sources and haven't been updated in 2+ weeks.

**Workflow**:
1. Identifies tenants without sources
2. Filters for tenants not updated in 2 weeks
3. Deletes tenant records
4. Clears tenant cache

---

### `masu.processor.tasks.validate_daily_data`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Validates data integrity between PostgreSQL and Trino tables.

**Key Parameters**:
- `schema` - Database schema
- `start_date` - Start date for validation
- `end_date` - End date for validation
- `provider_uuid` - Provider UUID
- `ocp_on_cloud_type` - OCP on cloud infrastructure type (optional)
- `context` - Context dictionary

**Feature Flag**: Requires validation to be enabled for the schema

---

## Provider Management Tasks

### `masu.celery.tasks.check_report_updates`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Scheduled task that initiates the report scanning and download process for all providers.

**Workflow**:
1. Creates an Orchestrator instance
2. Calls `prepare()` which:
   - Gets polling batch of providers
   - Starts manifest processing for each provider
   - Downloads new reports

---

### `masu.processor.tasks.mark_manifest_complete`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Marks a manifest and provider as complete after all processing is finished.

**Key Parameters**:
- `schema` - Database schema
- `provider_type` - Provider type
- `provider_uuid` - Provider UUID
- `ingress_report_uuid` - Ingress report UUID (optional)
- `tracing_id` - Tracing ID
- `manifest_list` - List of manifest IDs

**Workflow**:
1. Updates provider's `data_updated_timestamp`
2. Marks manifests as completed in the database
3. Marks ingress report as completed (if applicable)

---

### `masu.celery.tasks.delete_provider_async`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Asynchronously deletes a provider record from the database.

**Key Parameters**:
- `name` - Provider name
- `provider_uuid` - Provider UUID
- `schema_name` - Database schema

---

### `masu.celery.tasks.out_of_order_source_delete_async`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Handles deletion of sources that were deleted out of order.

**Key Parameters**:
- `source_id` - Source ID to delete

---

### `masu.celery.tasks.missing_source_delete_async`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Handles deletion of missing sources.

**Key Parameters**:
- `source_id` - Source ID to delete

---

## Cost Model Tasks

### `masu.processor.tasks.update_cost_model_costs`

**Module**: `koku/masu/processor/tasks.py`

**Queue**: `CostModelQueue.DEFAULT`

**Description**: Updates usage charge information using cost models. Required for all OCP providers even without a cost model (for default distribution).

**Key Parameters**:
- `schema_name` - Database schema
- `provider_uuid` - Provider UUID
- `start_date` - Start date (optional)
- `end_date` - End date (optional)
- `queue_name` - Queue override (optional)
- `synchronous` - Synchronous execution flag
- `tracing_id` - Tracing ID

**Workflow**:
1. Checks if task is already running or rate-limited
2. Calls `CostModelCostUpdater` to apply cost model rates
3. Updates provider's `data_updated_timestamp`

---

## HCS (Hybrid Committed Spend) Tasks

### `hcs.tasks.collect_hcs_report_data_from_manifest`

**Module**: `koku/hcs/tasks.py`

**Queue**: `hcs`

**Description**: Collects and processes HCS report data from manifests.

**Key Parameters**:
- `reports_to_hcs_summarize` - List of reports to process

**Supported Providers**:
- AWS
- Azure
- GCP

**Workflow**:
1. Deduplicates reports
2. Determines date ranges and finalization requirements
3. Triggers `collect_hcs_report_data` for each report

---

### `hcs.tasks.collect_hcs_report_data`

**Module**: `koku/hcs/tasks.py`

**Queue**: `hcs`

**Description**: Generates HCS reports for a specific provider and date range.

**Key Parameters**:
- `schema_name` - Database schema
- `provider_type` - Provider type
- `provider_uuid` - Provider UUID
- `start_date` - Start date (default: today - 2 days)
- `end_date` - End date (default: today)
- `tracing_id` - Tracing ID
- `finalize` - Finalization flag (default: False)

**Retry Configuration**:
- Auto-retries on `ClientError`
- Max retries: `settings.MAX_UPDATE_RETRIES`

**Feature Flag**: Requires `cost-management.backend.hcs-data-processor` Unleash flag or `ENABLE_HCS_DEBUG`

---

### `hcs.tasks.collect_hcs_report_finalization`

**Module**: `koku/hcs/tasks.py`

**Queue**: `hcs`

**Description**: Runs finalization for HCS reports. Typically scheduled for the 15th of each month.

**Key Parameters**:
- `month` - Month to finalize (optional)
- `year` - Year to finalize (optional, required with month)
- `provider_type` - Provider type filter (optional)
- `provider_uuid` - Provider UUID filter (optional)
- `schema_name` - Schema name filter (optional)
- `tracing_id` - Tracing ID

**Workflow**:
1. Determines finalization date (defaults to current month)
2. Filters providers based on parameters
3. Triggers `collect_hcs_report_data` with finalization flag for each provider

---

## Subscriptions (SUBS) Tasks

### `subs.tasks.extract_subs_data_from_reports`

**Module**: `koku/subs/tasks.py`

**Queue**: `subs_extraction`

**Description**: Extracts subscription data from processed reports and uploads to S3.

**Key Parameters**:
- `reports_to_extract` - List of reports to process
- `metered` - Metered flag from provider data source

**Supported Providers**: Configured via `ENABLE_SUBS_PROVIDER_TYPES` environment variable

**Feature Flag**: Requires `cost-management.backend.subs-data-extraction` Unleash flag or `ENABLE_SUBS_DEBUG` or `metered == "rhel"`

**Workflow**:
1. Deduplicates reports
2. Validates provider type is enabled
3. Extracts subscription data to S3
4. Triggers messaging task if messaging is enabled

---

### `subs.tasks.process_upload_keys_to_subs_message`

**Module**: `koku/subs/tasks.py`

**Queue**: `subs_transmission`

**Description**: Processes S3 subscription data and sends messages to Kafka.

**Key Parameters**:
- `context` - Context dictionary
- `schema_name` - Database schema
- `tracing_id` - Tracing ID
- `upload_keys` - List of S3 keys to process

**Feature Flag**: Requires `cost-management.backend.subs-data-messaging` Unleash flag or `ENABLE_SUBS_DEBUG`

---

## Sources Tasks

### `sources.tasks.delete_source`

**Module**: `koku/sources/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Deletes a provider and its associated source record.

**Key Parameters**:
- `source_id` - Source ID
- `auth_header` - Authentication header
- `koku_uuid` - Provider UUID
- `account_number` - Account number
- `org_id` - Organization ID

**Retry Configuration**:
- Auto-retries on `ProviderProcessingError`
- Max retries: `settings.MAX_SOURCE_DELETE_RETRIES`
- Exponential backoff enabled

**Workflow**:
1. Marks provider as inactive
2. Calls `SourcesProviderCoordinator.destroy_account()`
3. Deletes provider and source records

---

### `sources.tasks.delete_source_beat`

**Module**: `koku/sources/tasks.py`

**Queue**: `SummaryQueue.DEFAULT`

**Description**: Scheduled task that processes sources marked for deletion.

**Workflow**:
1. Loads providers marked with `pending_delete=True`
2. Queues `delete_source` for each provider

---

### `sources.tasks.source_status_beat`

**Module**: `koku/sources/tasks.py`

**Queue**: `PriorityQueue.DEFAULT`

**Description**: Scheduled task that pushes source status updates.

**Workflow**:
1. Retrieves all sources with source_id
2. Pushes status update for each source via `SourceStatus`

---

## Scheduled Beat Tasks

The following tasks are scheduled via Celery Beat in `koku/koku/celery.py`:

### Report Download Schedule

**Task**: `masu.celery.tasks.check_report_updates`

**Schedule**: Configured via `REPORT_DOWNLOAD_SCHEDULE` (default: hourly `0 * * * *`)

**Enabled**: When `SCHEDULE_REPORT_CHECKS` environment variable is `True`

---

### Expired Data Removal

**Task**: `masu.celery.tasks.remove_expired_data`

**Schedule**: Configured via `REMOVE_EXPIRED_REPORT_DATA_ON_DAY` (default: 1st of month) and `REMOVE_EXPIRED_REPORT_UTC_TIME` (default: 00:00)

**Enabled**: When `REMOVE_EXPIRED_REPORT_DATA_ON_DAY != 0`

---

### Autovacuum Tuning

**Task**: `masu.celery.tasks.autovacuum_tune_schemas`

**Schedule**: Configured via `VACUUM_DATA_DAY_OF_WEEK` and `VACUUM_DATA_UTC_TIME` (default: daily at 00:00)

**Always Enabled**: Yes

---

### Source Deletion

**Task**: `sources.tasks.delete_source_beat`

**Schedule**: Daily at 04:00 (`0 4 * * *`)

**Always Enabled**: Yes

---

### Source Status Push

**Task**: `sources.tasks.source_status_beat`

**Schedule**: Configured via `SOURCE_STATUS_SCHEDULE` (default: daily at 03:00 `0 3 * * *`)

**Always Enabled**: Yes

---

### Azure Storage Capacity Scraping

**Task**: `masu.celery.tasks.scrape_azure_storage_capacities`

**Schedule**: Daily at 02:00

**Always Enabled**: Yes

**Description**: Scrapes Azure disk capacity information from Azure documentation.

---

### Account Hierarchy Crawling

**Task**: `masu.celery.tasks.crawl_account_hierarchy`

**Schedule**: Daily at 00:00

**Always Enabled**: Yes

**Description**: Crawls AWS organization structure for account hierarchy.

---

### Currency Exchange Rates

**Task**: `masu.celery.tasks.get_daily_currency_rates`

**Schedule**: Daily at 01:00

**Always Enabled**: Yes

**Description**: Fetches latest currency exchange rates.

---

### HCS Report Finalization

**Task**: `hcs.tasks.collect_hcs_report_finalization`

**Schedule**: 15th of each month at 00:00

**Always Enabled**: Yes

---

### Delayed Task Trigger

**Task**: `masu.celery.tasks.trigger_delayed_tasks`

**Schedule**: Configured via `DELAYED_TASK_POLLING_MINUTES` (default: every 30 minutes)

**Always Enabled**: Yes

**Description**: Processes delayed/deferred Celery tasks.

---

## Additional Utility Tasks

### `masu.celery.tasks.collect_queue_metrics`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Collects Celery queue depth metrics for monitoring.

**Returns**: Dictionary of queue names to queue lengths

---

### `masu.celery.tasks.get_celery_queue_items`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Retrieves detailed information about tasks in queues.

**Key Parameters**:
- `queue_name` - Specific queue to inspect (optional)
- `task_name` - Specific task to filter by (optional)

**Returns**: Dictionary of queue names to task information

---

### `masu.celery.tasks.trigger_delayed_tasks`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DownloadQueue.DEFAULT`

**Description**: Triggers execution of delayed Celery tasks.

**Workflow**:
1. Calls `DelayedCeleryTasks.trigger_delayed_tasks()`
2. Removes expired delay records
3. Executes ready tasks

---

### `masu.celery.tasks.get_daily_currency_rates`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Fetches and updates daily currency exchange rates.

**Configuration**:
- URL: `settings.CURRENCY_URL`
- Retry strategy: 5 retries with exponential backoff

**Workflow**:
1. Fetches exchange rates from external API
2. Updates `ExchangeRates` model for valid currencies
3. Updates exchange rate cache

---

### `masu.celery.tasks.scrape_azure_storage_capacities`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Scrapes Azure disk capacity information from Azure documentation.

**Workflow**:
1. Uses `AzureDiskSizeScraper` to fetch disk sizes
2. Creates/updates `DiskCapacity` records

---

### `masu.celery.tasks.crawl_account_hierarchy`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Crawls top-level accounts to discover organizational hierarchy.

**Key Parameters**:
- `provider_uuid` - Specific provider to crawl (optional, defaults to all)

**Supported Providers**: AWS (via `AWSOrgUnitCrawler`)

---

### `masu.celery.tasks.check_cost_model_status`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Checks OCP providers without cost models and fires notifications.

**Key Parameters**:
- `provider_uuid` - Specific provider to check (optional, defaults to all OCP providers)

**Workflow**:
1. Filters OCP providers without infrastructure_id
2. Checks if cost model exists
3. Fires notification if missing

---

### `masu.celery.tasks.check_for_stale_ocp_source`

**Module**: `koku/masu/celery/tasks.py`

**Queue**: `DEFAULT`

**Description**: Checks for OpenShift sources that haven't uploaded data recently and fires notifications.

**Key Parameters**:
- `provider_uuid` - Specific provider to check (optional)

**Workflow**:
1. Gets last manifest upload datetime for providers
2. Checks if upload was more than 3 days ago
3. Fires stale source notification

---

## Queue Configuration

### Queue Types

Koku uses multiple queue types to organize task processing:

1. **DEFAULT** - General purpose tasks
2. **DownloadQueue**:
   - `DEFAULT` - Standard download priority
   - `XL` - Extra-large provider downloads
   - `PRIORITY` - High-priority downloads
3. **SummaryQueue**:
   - `DEFAULT` - Standard summary priority
   - `XL` - Extra-large provider summaries
   - `PRIORITY` - High-priority summaries
4. **CostModelQueue**:
   - `DEFAULT` - Standard cost model updates
   - `XL` - Extra-large provider cost models
   - `PRIORITY` - High-priority cost model updates
5. **RefreshQueue**:
   - `DEFAULT` - Standard refresh operations
   - `XL` - Extra-large provider refreshes
   - `PRIORITY` - High-priority refreshes
6. **OCPQueue**:
   - `DEFAULT` - OpenShift-specific processing
   - `XL` - Extra-large OCP providers
   - `PRIORITY` - High-priority OCP processing
7. **PriorityQueue**:
   - `DEFAULT` - High-priority general tasks
   - `XL` - Extra-large high-priority tasks
   - `PRIORITY` - Highest priority tasks
8. **HCS_QUEUE** (`hcs`) - Hybrid Committed Spend processing
9. **SUBS_EXTRACTION_QUEUE** (`subs_extraction`) - Subscription data extraction
10. **SUBS_TRANSMISSION_QUEUE** (`subs_transmission`) - Subscription data messaging

### Queue Selection Logic

Queue selection is dynamic based on:
- **Customer Size**: Large customers (determined by report count threshold `XL_REPORT_COUNT`) use XL queues
- **Provider Type**: OCP providers use OCPQueue for certain operations
- **Priority Override**: Tasks can specify a priority queue via `queue_name` parameter
- **Rate Limiting**: Large customers may be rate-limited to prevent resource exhaustion

### Customer Queue Determination

The `get_customer_queue()` function (in `common.queues`) determines the appropriate queue based on:
1. Schema name (customer identifier)
2. Base queue type
3. XL provider flag (for very large providers)

---

## Task Dependencies and Workflows

### Standard Report Processing Flow

```
check_report_updates (Beat Schedule)
  └─> Orchestrator.prepare()
      └─> start_manifest_processing()
          └─> get_report_files (Download) [per file]
              └─> _get_report_files (download)
              └─> _process_report_file (convert to Parquet)
              └─> Chord completion triggers:
                  ├─> summarize_reports
                  │   └─> update_summary_tables [per provider/date range]
                  │       ├─> update_openshift_on_cloud (for OCP on Cloud)
                  │       │   └─> update_cost_model_costs (OCP)
                  │       ├─> update_cost_model_costs (for OCP)
                  │       ├─> mark_manifest_complete
                  │       └─> validate_daily_data
                  ├─> collect_hcs_report_data_from_manifest
                  │   └─> collect_hcs_report_data
                  └─> extract_subs_data_from_reports
                      └─> process_upload_keys_to_subs_message
```

### Source Deletion Flow

```
delete_source_beat (Beat Schedule)
  └─> delete_source [per provider]
      └─> SourcesProviderCoordinator.destroy_account()
          └─> delete_archived_data (async)
```

---

## Performance Considerations

### Task Deduplication

Several tasks implement deduplication to prevent concurrent execution:
- `update_summary_tables` - Uses `WorkerCache` to track running tasks
- `update_openshift_on_cloud` - Uses `WorkerCache` for deduplication
- `update_cost_model_costs` - Uses `WorkerCache` for deduplication

### Rate Limiting

Large customers are rate-limited to prevent resource exhaustion:
- Checked via `is_rate_limit_customer_large(schema)`
- Implemented via `rate_limit_tasks(task_name, schema)`
- Tasks are requeued when rate-limited

### Worker Configuration

- **Max tasks per worker**: Configured via `MAX_CELERY_TASKS_PER_WORKER` (default: 10)
- **Worker alive timeout**: Configured via `WORKER_PROC_ALIVE_TIMEOUT` (default: 4 seconds)
- **Broker retry**: Max 4 retries with exponential backoff (max 3 seconds)

---

## Monitoring and Debugging

### Tracing

All tasks support tracing via `tracing_id` parameter:
- Used for correlating log entries
- Typically set to `manifest_id`, `request_id`, or generated UUID
- Included in all structured log messages via `log_json()`

### Metrics

Tasks expose Prometheus metrics:
- `GET_REPORT_ATTEMPTS_COUNTER` - Report download attempts
- `REPORT_FILE_DOWNLOAD_ERROR_COUNTER` - Download errors
- `PROCESS_REPORT_ATTEMPTS_COUNTER` - Processing attempts
- `PROCESS_REPORT_ERROR_COUNTER` - Processing errors
- `REPORT_SUMMARY_ATTEMPTS_COUNTER` - Summary attempts
- `COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER` - Cost model update attempts

### Task Inspection

Use `get_celery_queue_items` task to inspect queue contents:
```python
from masu.celery.tasks import get_celery_queue_items

# Get all tasks in all queues
get_celery_queue_items.delay()

# Get tasks in specific queue
get_celery_queue_items.delay(queue_name='summary')

# Get specific task type
get_celery_queue_items.delay(task_name='masu.processor.tasks.update_summary_tables')
```

---

## Error Handling

### Automatic Retries

Tasks with automatic retry configuration:
- `get_report_files` - Retries on Trino 404 errors
- `update_openshift_on_cloud` - Retries on cloud correlation errors
- `delete_archived_data` - Retries on AWS client errors
- `delete_source` - Retries on provider processing errors
- `collect_hcs_report_data` - Retries on AWS client errors

### Error Logging

All tasks use the `LogErrorsTask` base class which:
- Logs exceptions with full context
- Identifies foreign key violations
- Integrates with Sentry for error tracking

### Failure Recovery

- Manifest processing failures update manifest state to `FAILED`
- Tasks check for disabled sources/schemas before processing
- WorkerCache is cleaned up on task failure

---

## Feature Flags

Several tasks respect Unleash feature flags:

- **HCS Processing**: `cost-management.backend.hcs-data-processor`
- **SUBS Extraction**: `cost-management.backend.subs-data-extraction`
- **SUBS Messaging**: `cost-management.backend.subs-data-messaging`
- **Trino File Purging**: `enable-purge-turnpikes`

---

## Environment Variables

Key environment variables affecting task behavior:

- `SCHEDULE_REPORT_CHECKS` - Enable scheduled report checks
- `REPORT_DOWNLOAD_SCHEDULE` - Cron schedule for report downloads
- `REMOVE_EXPIRED_REPORT_DATA_ON_DAY` - Day of month for data removal
- `REMOVE_EXPIRED_REPORT_UTC_TIME` - Time for data removal
- `VACUUM_DATA_DAY_OF_WEEK` - Day for autovacuum tuning
- `VACUUM_DATA_UTC_TIME` - Time for autovacuum tuning
- `SOURCE_STATUS_SCHEDULE` - Schedule for source status pushes
- `DELAYED_TASK_POLLING_MINUTES` - Interval for delayed task checking
- `MAX_CELERY_TASKS_PER_WORKER` - Worker recycling threshold
- `WORKER_PROC_ALIVE_TIMEOUT` - Worker startup timeout
- `MAX_UPDATE_RETRIES` - Maximum retry attempts for updates
- `MAX_SOURCE_DELETE_RETRIES` - Maximum retry attempts for source deletion
- `XL_REPORT_COUNT` - Threshold for marking provider as XL
- `AUTOVACUUM_TUNING` - Custom autovacuum thresholds (JSON)
- `ENABLE_HCS_DEBUG` - Enable HCS processing debugging
- `ENABLE_SUBS_DEBUG` - Enable SUBS processing debugging
- `ENABLE_SUBS_PROVIDER_TYPES` - List of providers enabled for SUBS

---

## Document Version

- **Last Updated**: 2025-10-21
- **Koku Version**: Current (as of document creation)
- **Total Tasks Documented**: 50+
