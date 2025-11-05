# PostgreSQL Pipeline Implementation Summary

## Overview

This document summarizes the implementation of the PostgreSQL-based OCP ingestion pipeline for on-premises deployments. The implementation allows the codebase to support both Trino (SaaS) and PostgreSQL (on-prem) pipelines via configuration.

## Components Implemented

### 1. **Architecture Documentation** ✅
- **File**: `docs/architecture/ocp-postgres-pipeline.md`
- **Content**: Comprehensive documentation covering:
  - Pipeline comparison (Trino vs PostgreSQL)
  - Component architecture
  - Data flow diagrams
  - Performance characteristics
  - Migration strategy

### 2. **Database Migration** ✅
- **File**: `koku/reporting/migrations/0339_ocp_postgres_staging_tables.py`
- **Content**: Creates 5 staging tables:
  - `reporting_ocpusagelineitem_pod_staging`
  - `reporting_ocpusagelineitem_storage_staging`
  - `reporting_ocpusagelineitem_node_labels_staging`
  - `reporting_ocpusagelineitem_namespace_labels_staging`
  - `reporting_ocpusagelineitem_vm_staging`
- **Features**:
  - Partitioned by `interval_start` (monthly partitions)
  - Indexed for fast querying
  - Includes metadata columns (`report_period_id`, `source_uuid`, `processed`)

### 3. **PostgreSQL Aggregation Function** ✅
- **File**: `koku/masu/database/sql/openshift/populate_daily_summary_from_staging.sql`
- **Functionality**:
  - Aggregates hourly data to daily summaries
  - Joins pod, storage, node labels, and namespace labels
  - Filters labels to enabled keys
  - Converts units (seconds→hours, bytes→GB)
  - Calculates node and cluster capacity
  - Merges labels from all sources
  - Marks processed data

### 4. **CSV Processor** ✅
- **File**: `koku/masu/processor/ocp/ocp_postgres_report_processor.py`
- **Class**: `OCPPostgresReportProcessor`
- **Functionality**:
  - Reads CSV files with pandas
  - Calculates effective usage (min of usage and request)
  - Filters labels to enabled keys
  - Bulk loads into staging tables via PostgreSQL COPY
  - Tracks processing status

### 5. **Summary Updater** ✅
- **File**: `koku/masu/processor/ocp/ocp_postgres_summary_updater.py`
- **Class**: `OCPPostgresSummaryUpdater`
- **Functionality**:
  - Checks for staging data availability
  - Ensures partitions exist
  - Calls PostgreSQL aggregation function
  - Populates UI summary tables
  - Handles label summaries
  - Checks for cloud infrastructure

### 6. **Database Accessor Methods** ✅
- **File**: `koku/masu/database/ocp_report_db_accessor.py`
- **Methods Added**:
  - `get_enabled_tags()` - Query enabled tag keys
  - `populate_daily_summary_from_staging()` - Call PostgreSQL aggregation
  - `cleanup_staging_tables()` - Clean up old partitions

### 7. **Settings/Feature Flag** ✅
- **File**: `koku/koku/settings.py`
- **Setting**: `OCP_POSTGRES_PIPELINE`
- **Default**: `False` (Trino pipeline)
- **Environment Variable**: `OCP_POSTGRES_PIPELINE=true` for PostgreSQL pipeline

### 8. **Routing Logic** (To Be Completed)
- **Location**: `koku/masu/processor/report_summary_updater.py`
- **Implementation Needed**:

```python
# In ReportSummaryUpdater._set_updater() method
if self.provider_type in Provider.OPENSHIFT_PROVIDER_LIST:
    if settings.OCP_POSTGRES_PIPELINE:
        # Use PostgreSQL pipeline
        from masu.processor.ocp.ocp_postgres_summary_updater import OCPPostgresSummaryUpdater
        self._updater = OCPPostgresSummaryUpdater(
            self._schema, self._provider, self._manifest
        )
    else:
        # Use Trino pipeline (default)
        from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
        self._updater = OCPReportParquetSummaryUpdater(
            self._schema, self._provider, self._manifest
        )
```

- **Location**: `koku/masu/processor/parquet/parquet_report_processor.py`
- **Implementation Needed** (in `convert_to_parquet()` method):

```python
# For OCP reports, check if we should use PostgreSQL pipeline
if self.provider_type == Provider.PROVIDER_OCP and settings.OCP_POSTGRES_PIPELINE:
    # Use PostgreSQL processor instead of Parquet
    from masu.processor.ocp.ocp_postgres_report_processor import OCPPostgresReportProcessor

    for csv_filename in file_list:
        processor = OCPPostgresReportProcessor(
            manifest_id=self._manifest_id,
            account=self.account,
            s3_path=str(csv_filename),
            provider_uuid=self._provider_uuid,
            local_path=csv_filename,
            report_type=self.report_type
        )
        processor.process()
    return True
```

## Configuration

### Environment Variables

```bash
# Enable PostgreSQL pipeline (on-prem)
export OCP_POSTGRES_PIPELINE=true

# Or keep default Trino pipeline (SaaS)
export OCP_POSTGRES_PIPELINE=false
```

### Database Setup

1. Run migrations:
```bash
python manage.py migrate
```

2. Create initial partitions (automatic on first use)

3. Configure retention:
```python
# Default: 7 days
accessor.cleanup_staging_tables(retention_days=7)
```

## Testing

### Unit Tests (To Be Completed)

Test files to create:
- `koku/masu/test/processor/ocp/test_ocp_postgres_report_processor.py`
- `koku/masu/test/processor/ocp/test_ocp_postgres_summary_updater.py`
- `koku/masu/test/database/test_ocp_report_db_accessor_postgres.py`

Test scenarios:
1. CSV loading with various data formats
2. Effective usage calculation
3. Label filtering logic
4. Staging table bulk insert
5. SQL function aggregation logic
6. Error handling and recovery
7. Data parity with Trino pipeline

## Migration Path

### Phase 1: Development & Testing
1. ✅ Implement core components
2. ⏳ Complete routing logic
3. ⏳ Create unit tests
4. Run integration tests
5. Validate data parity with Trino

### Phase 2: Staging Deployment
1. Deploy to staging environment
2. Enable for test customers
3. Monitor metrics and errors
4. Performance tuning

### Phase 3: Production Rollout
1. Document configuration
2. Gradual rollout to on-prem customers
3. Monitor and address issues
4. Collect feedback

## Performance Expectations

| Cluster Size | Processing Time | Staging Storage | Summary Storage |
|--------------|----------------|-----------------|-----------------|
| Small (10 nodes, 100 pods) | 15-30 seconds | ~10 MB/day | ~1 MB/day |
| Medium (50 nodes, 500 pods) | 60-120 seconds | ~50 MB/day | ~5 MB/day |
| Large (200 nodes, 2K pods) | 180-360 seconds | ~200 MB/day | ~20 MB/day |

## Known Limitations

1. **Scalability**: PostgreSQL pipeline may be slower for very large clusters (>1000 nodes)
2. **OCP-on-Cloud**: Still uses Trino for matching cloud provider data
3. **Parquet Data**: Not created in PostgreSQL pipeline (not needed for on-prem)

## Future Enhancements

1. Incremental aggregation (only reaggregate changed dates)
2. Parallel processing of multiple report types
3. Table compression for staging tables
4. Materialized views for complex aggregations
5. Hybrid approach: PostgreSQL for most, Trino for largest customers

## Remaining Tasks

### Critical (Must Complete)
1. ⏳ **Routing Logic**: Add pipeline selection in `ReportSummaryUpdater` and `ParquetReportProcessor`
2. ⏳ **Unit Tests**: Create comprehensive test suite
3. ⏳ **Integration Tests**: Validate end-to-end processing
4. ⏳ **Data Parity Validation**: Ensure both pipelines produce identical results

### Nice to Have
1. Performance benchmarks
2. Monitoring dashboards
3. Troubleshooting guide
4. Customer migration documentation

## References

- Architecture Doc: `docs/architecture/ocp-postgres-pipeline.md`
- Original Trino Pipeline Doc: `docs/architecture/csv-processing-ocp.md`
- Django Migration: `koku/reporting/migrations/0339_ocp_postgres_staging_tables.py`
- Settings: `koku/koku/settings.py` (line ~610)

## Contact

For questions or issues:
- Review architecture documentation
- Check implementation files
- Consult with development team
