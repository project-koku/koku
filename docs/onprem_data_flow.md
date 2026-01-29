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
│   │ 3. create_parquet_table()  [if table doesn't exist]                                 │ │
│   │    • Creates schema (if needed)                                                      │ │
│   │    • Creates partitioned table in PostgreSQL                                         │ │
│   │    • Creates partition for source/year/month                                         │ │
│   └─────────────────────────────────────────────────────────────────────────────────────┘ │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│   │ 4. _write_dataframe()                                                               │ │
│   │    • Calls processor.write_dataframe_to_sql()                                       │ │
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

### Raw Line Items (partitioned by source, year, month)

| Table Name | Description |
|------------|-------------|
| `openshift_pod_usage_line_items_daily` | OCP pod usage data |
| `openshift_storage_usage_line_items_daily` | OCP storage usage data |
| `openshift_node_labels_line_items_daily` | OCP node labels |
| `aws_line_items` | AWS cost/usage data |
| `azure_line_items` | Azure cost/usage data |
| `gcp_line_items` | GCP cost/usage data |

### Summary Tables (populated by summarization SQL)

| Table Name | Description |
|------------|-------------|
| `reporting_ocpusagelineitem_daily_summary` | OCP daily summary |
| `reporting_awscostentrylineitem_daily_summary` | AWS daily summary |
| `reporting_ocpawscostlineitem_project_daily_summary_p` | OCP-on-AWS project summary |
| `reporting_ocpgcpcostlineitem_project_daily_summary_p` | OCP-on-GCP project summary |
| `reporting_ocpazurecostlineitem_project_daily_summary_p` | OCP-on-Azure project summary |

## Key ONPREM vs CLOUD Differences

| Aspect | CLOUD (Trino/S3) | ONPREM (PostgreSQL) |
|--------|------------------|---------------------|
| Data Storage | Writes parquet files to S3 | Writes directly to PostgreSQL tables |
| Table Creation | Creates Hive tables in Trino | Creates partitioned Postgres tables |
| Partition Sync | `sync_hive_partitions()` | `create_report_partition()` |
| Data Write | `_write_parquet_to_file()` | `write_dataframe_to_sql()` |
| Queries | Via Trino | Via Django ORM / raw SQL |

## Key Files

| File | Purpose |
|------|---------|
| `masu/external/kafka_msg_handler.py` | Handles Kafka messages, downloads/extracts tar.gz |
| `masu/processor/parquet/parquet_report_processor.py` | Main processor, orchestrates CSV → DB flow |
| `masu/processor/report_parquet_processor_base.py` | Base processor with table creation and data writing |
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
6. **Delete old data** from postgres for this source/year/month
7. **Read CSV in chunks** using pandas
8. **Create postgres table** (partitioned by source/year/month) if needed
9. **Write dataframe to SQL** using pandas `to_sql()` directly to partition
10. **Write daily aggregates** to daily summary tables
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
