# KOKU Data Flow (ONPREM Mode)

## Overview

This document describes the data flow from tar.gz ingestion to PostgreSQL tables, as implemented in commits starting from `133173f85` ("replace trino connections with django").

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           KOKU DATA FLOW (ONPREM MODE)                                  │
│                        tar.gz → CSV → PostgreSQL Tables                                 │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  Kafka Message   │  Message with URL to tar.gz in quarantine bucket
│  (platform.      │  Contains: request_id, url, b64_identity, account, org_id
│   upload.hccm)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ download_payload │  Downloads tar.gz from URL to temp directory
│                  │  (kafka_msg_handler.py:248)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ extract_payload  │  Extracts tar.gz → manifest.json + *.csv files
│ _contents        │  (kafka_msg_handler.py:279)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ extract_payload  │  • Parses manifest.json
│                  │  • Looks up provider by cluster_id
│                  │  • Creates CostUsageReportManifest record
│                  │  • Copies CSV files to destination directory
│                  │  (kafka_msg_handler.py:307)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ create_daily_    │  Splits CSV by date (if needed)
│ archives         │  Creates daily CSV files from incoming report
│                  │  (kafka_msg_handler.py:131)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ process_report   │  Calls _process_report_file()
│                  │  (kafka_msg_handler.py:604)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                   ParquetReportProcessor.process()                                        │
│                   (parquet_report_processor.py:631)                                       │
└────────┬─────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                   convert_to_parquet()                                                    │
│                   (parquet_report_processor.py:332)                                       │
│                                                                                           │
│   For each CSV file:                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 1. _delete_old_data_postgres()                                                      │ │
│   │    • Deletes existing data for this source/year/month                               │ │
│   │    • Uses get_delete_day_by_manifestid_sql()                                        │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 2. convert_csv_to_parquet()                                                         │ │
│   │    • Reads CSV in chunks (pd.read_csv with chunksize)                               │ │
│   │    • post_processor.process_dataframe() - transforms data                           │ │
│   │    • Generates column names                                                          │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 3. Tables created by Django migrations                                              │ │
│   │    • Parent tables created during migration (self_hosted_models.py)                 │ │
│   │    • Partitions created automatically by PostgreSQL trigger on insert               │ │
│   │    • Partition naming: tablename_YYYY_MM (e.g., openshift_pod_usage_line_items_     │ │
│   │      daily_2025_01)                                                                 │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 4. _write_dataframe()                                                               │ │
│   │    • Calls processor.write_to_self_hosted_table()                                   │ │
│   │    • Adds partition columns: year, month, source                                    │ │
│   │    • Uses pandas to_sql() to insert into partition table                            │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 5. handle_daily_frames_postgres()  [for daily aggregates]                           │ │
│   │    • Creates daily table partition                                                   │ │
│   │    • Writes aggregated daily data to postgres                                       │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│ summarize_       │  Triggers Celery task: summarize_reports
│ manifest         │  (kafka_msg_handler.py:515)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                   SUMMARIZATION (Celery Tasks)                                            │
│                                                                                           │
│   • update_summary_tables task                                                            │
│   • Runs SQL from self_hosted_sql/ folder                                                 │
│   • Populates summary tables (e.g., reporting_ocpusagelineitem_                           │
│     daily_summary, reporting_ocpaws*, reporting_ocpgcp*, etc.)                            │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## PostgreSQL Tables

> **Note:** On-prem currently only supports OCP (OpenShift Container Platform). AWS, Azure, and GCP are not supported.

### OCP Line Item Tables (partitioned by usage_start date)

| Table Name | Description |
|------------|-------------|
| `openshift_pod_usage_line_items` | Raw OCP pod usage data |
| `openshift_pod_usage_line_items_daily` | Daily aggregated pod usage |
| `openshift_storage_usage_line_items` | Raw OCP storage usage data |
| `openshift_storage_usage_line_items_daily` | Daily aggregated storage usage |
| `openshift_node_labels_line_items` | Raw OCP node labels |
| `openshift_node_labels_line_items_daily` | Daily aggregated node labels |
| `openshift_namespace_labels_line_items` | Raw OCP namespace labels |
| `openshift_namespace_labels_line_items_daily` | Daily aggregated namespace labels |
| `openshift_vm_usage_line_items` | Raw OCP VM usage data |
| `openshift_vm_usage_line_items_daily` | Daily aggregated VM usage |
| `openshift_gpu_usage_line_items` | Raw OCP GPU usage data |
| `openshift_gpu_usage_line_items_daily` | Daily aggregated GPU usage |

### Staging Table (used during summarization)

| Table Name | Description |
|------------|-------------|
| `reporting_ocpusagelineitem_daily_summary_staging` | Intermediate staging table for aggregation during summarization |

### Summary Tables (populated by summarization SQL)

| Table Name | Description |
|------------|-------------|
| `reporting_ocpusagelineitem_daily_summary` | OCP daily summary (main summary table for UI) |

## Key ONPREM vs CLOUD Differences

| Aspect | CLOUD (Trino/S3) | ONPREM (PostgreSQL) |
|--------|------------------|---------------------|
| Data Storage | Writes parquet files to S3 | Writes directly to PostgreSQL tables |
| Table Creation | Creates Hive tables in Trino | Django migrations create partitioned tables |
| Partition Management | `sync_hive_partitions()` | Automatic via PostgreSQL trigger on insert |
| Data Write | `_write_parquet_to_file()` | `write_to_self_hosted_table()` |
| Source Deletion | `delete_hive_partitions_by_source()` | `delete_self_hosted_data_by_source()` |
| Expired Data Cleanup | Trino partition deletion | `PartitionedTable` based partition cleanup |
| Queries | Via Trino | Via Django ORM / raw SQL |
| Supported Providers | AWS, Azure, GCP, OCP | OCP only |

## Key Files

| File | Purpose |
|------|---------|
| `masu/external/kafka_msg_handler.py` | Handles Kafka messages, downloads/extracts tar.gz |
| `masu/processor/parquet/parquet_report_processor.py` | Main processor, orchestrates CSV → DB flow |
| `masu/processor/report_parquet_processor_base.py` | Base processor with table creation and data writing |
| `masu/processor/ocp/ocp_report_parquet_processor.py` | OCP-specific processor with `write_to_self_hosted_table()` |
| `masu/processor/ocp/ocp_report_db_cleaner.py` | Handles expired data and source deletion cleanup |
| `reporting/provider/ocp/self_hosted_models.py` | Django models for OCP line item and staging tables (on-prem) |
| `koku/reportdb_accessor.py` | Abstract interface for DB accessors |
| `koku/reportdb_accessor_postgres.py` | PostgreSQL-specific SQL generation |
| `koku/reportdb_accessor_trino.py` | Trino-specific SQL generation (cloud mode) |
| `masu/database/self_hosted_sql/` | SQL files for summarization queries |

## Flow Summary

1. **Kafka receives message** with URL to tar.gz payload
2. **Download** tar.gz from ingress quarantine bucket
3. **Extract** tar.gz → manifest.json + CSV files
4. **Parse manifest** and lookup provider by cluster_id
5. **Split CSVs by day** (if operator doesn't send daily reports)
6. **Delete old data** from postgres for this source/date range
7. **Read CSV in chunks** using pandas
8. **Create partition** (if needed) - PostgreSQL trigger creates partition on insert
9. **Write dataframe to SQL** using pandas `to_sql()` directly to table (routed to partition)
10. **Write daily aggregates** to daily line item tables
11. **Trigger summarization** Celery tasks to populate UI summary tables

## Related Commits

| Commit | Description |
|--------|-------------|
| `133173f85` | Replace trino connections with django (FLPATH-2826) |
| `df5bb010b` | Create tables, schemas and partitions in postgres (FLPATH-2893) |
| `3038ad061` | Delete old report data before processing (FLPATH-2946) |
| `ce73315b9` | Convert SQL files in trino_sql folders |
| `283bb8a0d` | Replace hard coded trino sql |
| `b2a990d5b` | Replace trino sql in migration tool (FLPATH-2957) |
| `0ca0e15f2` | Add MockUnleashClient for ONPREM mode |
| `d82c28cc8` | docker-compose file with onprem support |
| `75c5dc808` | Bug fixes after iqe tests (FLPATH-2822) |
