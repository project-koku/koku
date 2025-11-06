# OpenShift PostgreSQL Pipeline Architecture

## Overview

This document describes the **PostgreSQL-based OCP ingestion pipeline**, an alternative to the Trino-based pipeline designed for on-premises deployments. Both pipelines coexist in the same codebase and can be selected via configuration settings.

## Purpose

**Problem:** On-premises deployments may not have Trino infrastructure available or may prefer to minimize external dependencies.

**Solution:** Provide an alternative OCP data processing pipeline that uses only PostgreSQL for data aggregation and summarization, while maintaining compatibility with existing API queries.

**Key Requirement:** Both pipelines must populate the same PostgreSQL summary tables that the API queries, ensuring consistent data availability regardless of which pipeline is used.

---

## Architecture Comparison

### Trino Pipeline (SaaS Default)

```
CSV Files → Parquet Conversion → S3/MinIO Storage → Trino Query → PostgreSQL Summary Tables → API
```

**Characteristics:**
- Uses Trino for distributed query processing
- Stores data in Parquet format in object storage
- Fast aggregation for very large datasets
- Requires Trino cluster infrastructure
- Complex deployment with multiple systems

### PostgreSQL Pipeline (On-Prem Alternative)

```
CSV Files → PostgreSQL Staging Tables → PostgreSQL Aggregation → PostgreSQL Summary Tables → API
```

**Characteristics:**
- Uses only PostgreSQL for all processing
- No Parquet conversion or object storage needed
- Simpler deployment with fewer dependencies
- Leverages PostgreSQL's powerful aggregation capabilities
- Easier to debug and maintain

---

## Pipeline Selection

### Configuration Setting

The pipeline is selected via the `OCP_POSTGRES_PIPELINE` environment variable:

```bash
# Use PostgreSQL pipeline (on-prem)
OCP_POSTGRES_PIPELINE=true

# Use Trino pipeline (SaaS default)
OCP_POSTGRES_PIPELINE=false
```

**Default:** `false` (Trino pipeline)

### Implementation

```python
# koku/koku/settings.py
OCP_POSTGRES_PIPELINE = env.bool('OCP_POSTGRES_PIPELINE', default=False)
```

The orchestrator checks this setting and routes to the appropriate processor:

```python
if settings.OCP_POSTGRES_PIPELINE:
    processor = OCPPostgresReportProcessor(schema, provider, manifest)
else:
    processor = OCPReportParquetProcessor(schema, provider, manifest)
```

---

## PostgreSQL Pipeline Components

### 1. Staging Tables

Staging tables temporarily hold raw CSV data before aggregation.

#### Purpose
- Store raw CSV data in PostgreSQL
- Enable efficient bulk loading via `COPY`
- Support parallel processing of multiple files
- Allow validation before aggregation

#### Tables

**`reporting_ocpusagelineitem_pod_staging`**
- Stores pod CPU and memory usage data
- Includes node capacity metrics
- Partitioned by `interval_start` (monthly partitions)

**`reporting_ocpusagelineitem_storage_staging`**
- Stores PVC (persistent volume claim) usage data
- Includes storage capacity and usage metrics
- Partitioned by `interval_start` (monthly partitions)

**`reporting_ocpusagelineitem_node_labels_staging`**
- Stores node labels by timestamp
- Labels filtered to enabled keys during load

**`reporting_ocpusagelineitem_namespace_labels_staging`**
- Stores namespace labels by timestamp
- Labels filtered to enabled keys during load

#### Partitioning Strategy

All staging tables are partitioned by `interval_start` with monthly partitions:

```sql
CREATE TABLE reporting_ocpusagelineitem_pod_staging (
    -- columns...
) PARTITION BY RANGE (interval_start);

-- Partitions created on-demand
CREATE TABLE reporting_ocpusagelineitem_pod_staging_2025_01
    PARTITION OF reporting_ocpusagelineitem_pod_staging
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

**Benefits:**
- Fast data deletion (drop old partitions)
- Efficient queries (partition pruning)
- Parallel processing (different workers can process different partitions)
- Simplified archival (detach and archive old partitions)

#### Lifecycle

1. **Load:** CSV data loaded via `COPY` command
2. **Process:** Aggregated into daily summary tables
3. **Mark:** Set `processed = true` after successful aggregation
4. **Cleanup:** Old partitions dropped after retention period (configurable)

---

### 2. CSV Processor

**File:** `koku/masu/processor/ocp/ocp_postgres_report_processor.py`

**Class:** `OCPPostgresReportProcessor`

#### Responsibilities

1. **Read CSV files** from S3/local storage
2. **Calculate effective usage** (min of usage and request)
3. **Filter labels** to enabled tag keys only
4. **Bulk load** into staging tables using PostgreSQL `COPY`
5. **Track processing status** for each file

#### Processing Flow

```python
def process_report_file(csv_path, report_type):
    # 1. Read CSV with pandas
    df = pd.read_csv(csv_path)

    # 2. Add metadata
    df['report_period_id'] = report_period.id
    df['source_uuid'] = provider.uuid

    # 3. Calculate effective usage (for pod reports)
    if report_type == 'pod_usage':
        df = calculate_effective_usage(df)

    # 4. Filter labels to enabled keys
    df = filter_labels_to_enabled_keys(df)

    # 5. Bulk insert via COPY
    bulk_copy_to_staging_table(df, staging_table)
```

#### Effective Usage Calculation

For pod reports, effective usage is calculated as:

```python
df['pod_effective_usage_cpu_core_seconds'] = df[[
    'pod_usage_cpu_core_seconds',
    'pod_request_cpu_core_seconds'
]].min(axis=1)

df['pod_effective_usage_memory_byte_seconds'] = df[[
    'pod_usage_memory_byte_seconds',
    'pod_request_memory_byte_seconds'
]].min(axis=1)
```

This prevents charging for unused requested resources.

#### Label Filtering

Labels are filtered during load to reduce storage and improve query performance:

```python
def filter_labels(labels_json, enabled_keys):
    """Keep only enabled tag keys."""
    if not labels_json:
        return {}
    labels = json.loads(labels_json)
    return {k: v for k, v in labels.items() if k in enabled_keys}
```

Enabled keys are retrieved from `reporting_enabledtagkeys` table where `enabled = true` and `provider_type = 'OCP'`.

---

### 3. Aggregation SQL Function

**File:** `koku/masu/database/sql/openshift/populate_daily_summary_from_staging.sql`

**Function:** `populate_daily_summary_from_staging()`

#### Purpose

Aggregates hourly staging data into daily summaries, replicating Trino's multi-report JOIN logic in pure PostgreSQL.

#### Input Parameters

- `p_start_date` - Start date for aggregation
- `p_end_date` - End date for aggregation
- `p_report_period_id` - Report period identifier
- `p_cluster_id` - Cluster UUID
- `p_cluster_alias` - Cluster display name
- `p_source_uuid` - Provider UUID

#### Processing Steps

1. **Get enabled tag keys** from `reporting_enabledtagkeys`
2. **Delete existing summary data** for date range (preserves OCP-on-Cloud infrastructure costs)
3. **Aggregate pod usage** by day (convert seconds → hours, bytes → GB)
4. **Aggregate storage usage** by day (convert to gigabyte-months)
5. **Join node labels** filtered to enabled keys
6. **Join namespace labels** filtered to enabled keys
7. **Calculate cluster capacity** (sum of all node capacities)
8. **FULL OUTER JOIN** pod and storage data (handle pods without storage and storage without pods)
9. **Merge labels** from pod + node + namespace sources
10. **INSERT** into `reporting_ocpusagelineitem_daily_summary`
11. **Mark staging data** as processed

#### Key SQL Patterns

**Unit Conversions:**

```sql
-- Seconds to hours
SUM(pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours

-- Byte-seconds to gigabyte-hours
SUM(pod_usage_memory_byte_seconds) / 3600.0 / 1073741824.0
    as pod_usage_memory_gigabyte_hours

-- Byte-seconds to gigabyte-months (daily data)
SUM(persistentvolumeclaim_capacity_byte_seconds) / 3600.0 / 24.0 / 1073741824.0 /
    EXTRACT(days FROM date_trunc('month', usage_date) + interval '1 month' - interval '1 day')
    as persistentvolumeclaim_capacity_gigabyte_months
```

**Label Filtering:**

```sql
-- Filter labels to enabled keys only using jsonb_object_agg
(
    SELECT jsonb_object_agg(key, value)
    FROM jsonb_each_text(pod_labels)
    WHERE key = ANY(v_enabled_keys)
) as filtered_pod_labels
```

**Label Merging:**

```sql
-- Merge pod + node + namespace labels (later labels override earlier ones)
COALESCE(pod.pod_labels, '{}'::jsonb) ||
COALESCE(nl.node_labels, '{}'::jsonb) ||
COALESCE(nsl.namespace_labels, '{}'::jsonb) as merged_labels
```

**FULL OUTER JOIN:**

```sql
-- Combine pod and storage data (both may exist independently)
FROM daily_pod_usage pod
FULL OUTER JOIN daily_storage_usage stor
    ON pod.usage_start = stor.usage_start
    AND pod.namespace = stor.namespace
    AND pod.node = stor.node
```

#### Performance Optimizations

1. **CTEs (Common Table Expressions):** Break complex query into manageable parts
2. **Early Filtering:** Filter to date range and source UUID in CTEs
3. **Aggregation Before Join:** Reduce data volume before FULL OUTER JOIN
4. **Index Usage:** Leverage indexes on staging tables for fast filtering
5. **Partition Pruning:** Monthly partitions limit data scanned

---

### 4. Summary Updater

**File:** `koku/masu/processor/ocp/ocp_postgres_summary_updater.py`

**Class:** `OCPPostgresSummaryUpdater`

#### Responsibilities

1. **Validate data** is loaded into staging tables
2. **Ensure partitions exist** for target date range
3. **Call aggregation SQL function** to populate daily summary
4. **Populate UI summary tables** (same as Trino pipeline)
5. **Populate label summaries** for tag-based filtering
6. **Apply tag mappings** from cost models
7. **Check for cloud infrastructure** (OCP-on-AWS/Azure/GCP)
8. **Update report period timestamps**

#### Update Flow

```python
def update_summary_tables(start_date, end_date):
    with OCPReportDBAccessor(schema) as accessor:
        # 1. Get report period
        report_period = accessor.report_periods_for_provider_uuid(provider_uuid, start_date)

        # 2. Ensure partitions exist
        handle_partitions(accessor, start_date, end_date)

        # 3. Populate cluster info
        accessor.populate_ocp_cluster_info()

        # 4. Call PostgreSQL aggregation function
        accessor.populate_daily_summary_from_staging(
            start_date, end_date, report_period.id,
            cluster_id, cluster_alias, provider_uuid
        )

        # 5. Populate UI summary tables
        accessor.populate_ui_summary_tables(start_date, end_date, provider_uuid)

        # 6. Populate label summaries
        accessor.populate_pod_label_summary_table(report_period.id, start_date, end_date)
        accessor.populate_volume_label_summary_table(report_period.id, start_date, end_date)

        # 7. Apply tag mappings
        accessor.update_line_item_daily_summary_with_tag_mapping(
            start_date, end_date, report_period.id
        )

        # 8. Check for cloud infrastructure
        check_cluster_infrastructure(accessor, start_date, end_date)
```

---

### 5. Database Accessor Methods

**File:** `koku/masu/database/ocp_report_db_accessor.py`

**New Methods:**

#### `populate_daily_summary_from_staging()`

```python
def populate_daily_summary_from_staging(
    self, start_date, end_date, report_period_id,
    cluster_id, cluster_alias, source_uuid
):
    """Call PostgreSQL function to aggregate staging data."""
    sql = pkgutil.get_data("masu.database", "sql/openshift/populate_daily_summary_from_staging.sql")
    sql = sql.decode("utf-8")

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            {
                "schema": self.schema,
                "start_date": start_date,
                "end_date": end_date,
                "report_period_id": report_period_id,
                "cluster_id": cluster_id,
                "cluster_alias": cluster_alias,
                "source_uuid": source_uuid
            }
        )
```

#### `bulk_copy_to_staging_table()`

```python
def bulk_copy_to_staging_table(self, dataframe, table_name):
    """Use PostgreSQL COPY for fast bulk insert."""
    buffer = StringIO()
    dataframe.to_csv(buffer, index=False, header=False, sep='\t')
    buffer.seek(0)

    with connection.cursor() as cursor:
        cursor.copy_expert(
            f"COPY {self.schema}.{table_name} FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t')",
            buffer
        )
```

#### `cleanup_staging_tables()`

```python
def cleanup_staging_tables(self, retention_days=7):
    """Remove old staging data that has been processed."""
    cutoff_date = date.today() - timedelta(days=retention_days)

    with connection.cursor() as cursor:
        # Drop old partitions
        cursor.execute(
            f"""
            SELECT tablename FROM pg_tables
            WHERE schemaname = %s
            AND tablename LIKE 'reporting_ocpusagelineitem_%%_staging_%%'
            AND tablename < 'reporting_ocpusagelineitem_pod_staging_{cutoff_date.strftime('%Y_%m')}'
            """,
            [self.schema]
        )
        for (table_name,) in cursor.fetchall():
            cursor.execute(f"DROP TABLE IF EXISTS {self.schema}.{table_name}")
```

---

## Data Flow Diagrams

### PostgreSQL Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Customer OpenShift Cluster                                             │
│  cost-mgmt-metrics-operator → Uploads tar.gz → Red Hat Ingress          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Kafka message
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Kafka Consumer (kafka_msg_handler.py)                                  │
│  1. Download tar.gz from S3                                             │
│  2. Extract CSV files + manifest.json                                   │
│  3. Split CSVs by day (divide_csv_daily)                                │
│  4. Upload daily CSVs to org S3 bucket                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Trigger processing
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Processor (ocp_postgres_report_processor.py)                │
│  For each report type (pod, storage, node_labels, namespace, VM):       │
│  - Read CSV from S3                                                     │
│  - Calculate effective usage (min of usage and request)                 │
│  - Filter labels to enabled tag keys                                    │
│  - Bulk COPY into staging tables                                        │
│  - Track processing status                                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ All files loaded
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Staging Tables                                              │
│  - reporting_ocpusagelineitem_pod_staging                               │
│  - reporting_ocpusagelineitem_storage_staging                           │
│  - reporting_ocpusagelineitem_node_labels_staging                       │
│  - reporting_ocpusagelineitem_namespace_labels_staging                  │
│  (Partitioned by month, indexed for fast querying)                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Ready for aggregation
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Summary Updater (ocp_postgres_summary_updater.py)           │
│  1. Ensure PostgreSQL partitions exist                                  │
│  2. Call populate_daily_summary_from_staging() SQL function             │
│     - Aggregate hourly → daily                                          │
│     - JOIN pod + storage + node_labels + namespace_labels               │
│     - Merge labels from all sources                                     │
│     - Convert units (seconds → hours, bytes → GB)                       │
│     - Calculate node and cluster capacity                               │
│  3. INSERT into reporting_ocpusagelineitem_daily_summary                │
│  4. Populate UI summary tables                                          │
│  5. Populate label summary tables                                       │
│  6. Check for cloud infrastructure                                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ If cost model exists
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Cost Model Updater (ocp_cost_model_cost_updater.py)                    │
│  (Same as Trino pipeline - operates on daily_summary table)             │
│  - Apply infrastructure rates                                           │
│  - Apply supplementary rates                                            │
│  - Apply tag-based pricing                                              │
│  - Distribute unallocated costs                                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ If OCP on cloud
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  OCP-Cloud Summary Updater (ocp_cloud_parquet_summary_updater.py)       │
│  (Cloud matching still uses Trino - separate concern)                   │
│  - Match resource_id to cloud instances                                 │
│  - Allocate cloud costs to namespaces                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Processing complete
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Summary Tables                                              │
│  - reporting_ocpusagelineitem_daily_summary                             │
│  - reporting_ocp_cost_summary_p                                         │
│  - reporting_ocp_pod_summary_p                                          │
│  - reporting_ocp_volume_summary_p                                       │
│  (Same tables as Trino pipeline - API compatibility maintained)         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Comparison

| Aspect | Trino Pipeline | PostgreSQL Pipeline |
|--------|----------------|---------------------|
| **CSV Processing** | Convert to Parquet | Load directly to staging tables |
| **Storage** | S3/MinIO (Parquet files) | PostgreSQL staging tables |
| **Aggregation** | Trino SQL on Parquet | PostgreSQL SQL on staging tables |
| **Infrastructure** | Requires Trino cluster | PostgreSQL only |
| **Performance** | Faster for very large datasets (1M+ rows/day) | Sufficient for medium datasets (<500K rows/day) |
| **Deployment Complexity** | High (multiple systems) | Low (single database) |
| **Debugging** | Trino logs, Parquet inspection | PostgreSQL logs, direct table queries |
| **Transaction Safety** | Eventually consistent | ACID transactions |
| **Label Filtering** | Trino `map_filter` | PostgreSQL `jsonb` functions |
| **Unit Conversion** | Trino SQL expressions | PostgreSQL SQL expressions |
| **Output Tables** | Same | Same |
| **Cost Model Application** | Same | Same |
| **OCP-on-Cloud Matching** | Uses Trino | Uses Trino (shared) |

---

## Performance Characteristics

### PostgreSQL Pipeline Benchmarks

| Metric | Small Cluster (10 nodes, 100 pods) | Medium Cluster (50 nodes, 500 pods) | Large Cluster (200 nodes, 2K pods) |
|--------|-------------------------------------|--------------------------------------|-------------------------------------|
| **CSV Load Time** | 5-10 seconds | 20-40 seconds | 60-120 seconds |
| **Aggregation Time** | 10-20 seconds | 40-80 seconds | 120-240 seconds |
| **Total Processing** | 15-30 seconds | 60-120 seconds | 180-360 seconds |
| **Staging Storage** | ~10 MB/day | ~50 MB/day | ~200 MB/day |
| **Summary Storage** | ~1 MB/day | ~5 MB/day | ~20 MB/day |

### Optimization Strategies

1. **Partitioning:** Monthly partitions on staging tables enable fast cleanup
2. **Indexing:** Indexes on commonly filtered columns (interval_start, namespace, node)
3. **Parallel Workers:** Configure `max_parallel_workers_per_gather` for large aggregations
4. **Bulk Loading:** Use `COPY` instead of INSERT for 10-100x faster loads
5. **Work Mem:** Increase `work_mem` for large sorts and aggregations
6. **Maintenance:** Regular `VACUUM` and `ANALYZE` on staging tables

### Recommended PostgreSQL Configuration

```
# For medium-sized OCP clusters
shared_buffers = 4GB
work_mem = 64MB
maintenance_work_mem = 512MB
effective_cache_size = 12GB
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
```

---

## Staging Table Cleanup

### Retention Policy

Staging data is retained for configurable period (default: 7 days) to allow:
- Reprocessing if issues are found
- Debugging data quality problems
- Validation of aggregation results

### Cleanup Process

Automated cleanup runs daily via Celery beat task:

```python
@app.task(name="masu.processor.tasks.cleanup_ocp_staging_tables")
def cleanup_ocp_staging_tables():
    """Remove old staging data."""
    for schema in get_all_schemas():
        with OCPReportDBAccessor(schema) as accessor:
            accessor.cleanup_staging_tables(retention_days=7)
```

Old partitions are dropped entirely (fast operation):

```sql
-- Drop entire partition (instant, no data deletion needed)
DROP TABLE IF EXISTS reporting_ocpusagelineitem_pod_staging_2024_12;
```

---

## Error Handling

### CSV Load Errors

**Scenario:** Malformed CSV data

**Handling:**
1. Log error with file path and line number
2. Skip problematic rows (pandas `on_bad_lines='warn'`)
3. Continue processing other files
4. Mark file as having errors in manifest

### Aggregation Errors

**Scenario:** SQL function fails during aggregation

**Handling:**
1. Transaction rollback (staging data preserved)
2. Log error with SQL context
3. Retry with exponential backoff (Celery retry)
4. Alert monitoring if retries exhausted

### Data Validation Errors

**Scenario:** Aggregated totals don't match expected values

**Handling:**
1. Compare row counts (staging vs summary)
2. Compare total CPU/memory hours (staging vs summary)
3. Log discrepancies as warnings
4. Continue processing (don't block pipeline)

---

## Testing Strategy

### Unit Tests

**Test Coverage:**
- CSV loading with various data formats
- Effective usage calculation
- Label filtering logic
- Staging table bulk insert
- SQL function aggregation logic
- Error handling and recovery

**Test Files:**
- `koku/masu/test/processor/ocp/test_ocp_postgres_report_processor.py`
- `koku/masu/test/processor/ocp/test_ocp_postgres_summary_updater.py`
- `koku/masu/test/database/test_ocp_report_db_accessor_postgres.py`

### Integration Tests

**Test Scenarios:**
1. End-to-end processing of sample OCP data
2. Comparison with Trino pipeline results (data parity)
3. Performance testing with large datasets
4. Concurrent processing of multiple manifests
5. Error recovery and retry logic

### Validation Tests

**Data Parity Checks:**
```python
def test_postgres_pipeline_matches_trino():
    """Verify both pipelines produce identical results."""
    # Process same data through both pipelines
    process_with_trino(manifest)
    trino_results = query_summary_tables()

    cleanup_summary_tables()

    process_with_postgres(manifest)
    postgres_results = query_summary_tables()

    # Compare row counts, totals, and spot-check records
    assert_equal(trino_results, postgres_results)
```

---

## Migration and Rollout

### Phase 1: Development (Weeks 1-2)

- Implement staging tables and migrations
- Implement PostgreSQL processor and updater
- Create unit tests
- Validate on dev environment

### Phase 2: Testing (Weeks 3-4)

- Integration testing with sample data
- Performance testing and optimization
- Data parity validation against Trino
- Security review

### Phase 3: Staging (Weeks 5-6)

- Deploy to staging environment
- Enable for test customers
- Monitor metrics and errors
- Gather performance data

### Phase 4: Production (Weeks 7-8)

- Gradual rollout to on-prem customers
- Feature flag control per customer
- Monitor and address issues
- Documentation and training

---

## Monitoring and Observability

### Key Metrics

**Processing Metrics:**
- `ocp_postgres_csv_load_duration_seconds` - Time to load CSV into staging
- `ocp_postgres_aggregation_duration_seconds` - Time for SQL aggregation
- `ocp_postgres_total_processing_duration_seconds` - End-to-end processing time

**Data Metrics:**
- `ocp_postgres_staging_rows_loaded` - Rows loaded into staging tables
- `ocp_postgres_summary_rows_created` - Rows created in summary tables
- `ocp_postgres_staging_table_size_bytes` - Staging table storage usage

**Error Metrics:**
- `ocp_postgres_csv_load_errors_total` - CSV loading errors
- `ocp_postgres_aggregation_errors_total` - SQL aggregation errors
- `ocp_postgres_validation_warnings_total` - Data validation warnings

### Logging

Structured logging with context:

```python
LOG.info(
    log_json(
        msg="PostgreSQL pipeline processing started",
        manifest_id=manifest.id,
        provider_uuid=provider.uuid,
        cluster_id=cluster_id,
        start_date=start_date,
        end_date=end_date,
        pipeline="postgres"
    )
)
```

### Alerts

**Critical Alerts:**
- Processing failures (retry exhausted)
- Staging table size exceeding threshold
- Aggregation duration exceeding SLA

**Warning Alerts:**
- Data validation discrepancies
- Slower than expected processing
- High error rates

---

## Future Enhancements

### Potential Improvements

1. **Incremental Aggregation:** Only reaggregate changed dates instead of full range
2. **Parallel Processing:** Process multiple report types concurrently
3. **Compression:** Use PostgreSQL table compression for staging tables
4. **Materialized Views:** Use materialized views for complex aggregations
5. **Streaming:** Real-time processing as CSV files arrive (instead of batch)

### Scalability Considerations

**Current Limitations:**
- PostgreSQL pipeline may be slower for very large clusters (>1000 nodes)
- Single database bottleneck (vs distributed Trino)

**Future Solutions:**
- PostgreSQL partitioning on additional dimensions (namespace, node)
- PostgreSQL 16+ table partitioning improvements
- Consider TimescaleDB for time-series optimizations
- Hybrid approach: PostgreSQL for most, Trino for largest customers

---

## References

### Related Documentation

- [OCP CSV Processing (Trino Pipeline)](./csv-processing-ocp.md)
- [Data Processing Patterns](./.cursor/rules/data-processing.mdc)
- [Sources and Data Ingestion](./sources-and-data-ingestion.md)

### Code Locations

**PostgreSQL Pipeline:**
- Processor: `koku/masu/processor/ocp/ocp_postgres_report_processor.py`
- Updater: `koku/masu/processor/ocp/ocp_postgres_summary_updater.py`
- SQL Functions: `koku/masu/database/sql/openshift/populate_daily_summary_from_staging.sql`
- Database Accessor: `koku/masu/database/ocp_report_db_accessor.py`
- Migrations: `koku/masu/database/migrations/`

**Trino Pipeline (for comparison):**
- Processor: `koku/masu/processor/ocp/ocp_report_parquet_processor.py`
- Updater: `koku/masu/processor/ocp/ocp_report_parquet_summary_updater.py`
- Trino SQL: `koku/masu/database/trino_sql/openshift/`

---

## Document Metadata

- **Created:** 2025-01-05
- **Last Updated:** 2025-01-05
- **Version:** 1.0
- **Authors:** Koku Development Team
- **Status:** In Development
