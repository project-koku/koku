# Deep Dive: GCP BigQuery Export Processing in Koku

## **Overview**

Koku processes GCP billing data differently from AWS and Azure. Instead of downloading pre-generated CSV files, Koku **queries BigQuery directly** to extract billing data, then converts it to CSV, splits it by date, transforms to Parquet, and summarizes using Trino SQL. This "query-first" approach leverages GCP's BigQuery billing export as the source of truth.

---

## **GCP BigQuery Export Structure**

### **BigQuery Export Configuration**
- **Source:** GCP exports billing data to BigQuery tables automatically
- **Table Name:** `{project_id}.{dataset_id}.{table_id}`
- **Partitioning:** BigQuery tables are partitioned by `_PARTITIONTIME`
- **Export Frequency:** Continuous (data appears within hours)
- **Data Format:** Structured BigQuery table, not CSV files

### **Key BigQuery Columns (~50 columns)**

GCP extracts approximately 50 columns from BigQuery, including billing account, service details, project information, labels (JSON), location, cost, usage metrics, credits (JSON array), invoice month, and resource identifiers.

**Implementation:** See [`GCP_COLUMN_LIST`](../../koku/masu/util/gcp/common.py) in `koku/masu/util/gcp/common.py`

**Key Columns:**
- `billing_account_id` - GCP billing account
- `service.id`, `service.description` - Service details
- `sku.id`, `sku.description` - SKU details
- `usage_start_time`, `usage_end_time`, `export_time` - Timestamps
- `project.id`, `project.name`, `project.labels` - Project info
- `labels`, `system_labels` - JSON customer and system labels
- `location.*` - Location hierarchy (location, country, region, zone)
- `cost`, `currency`, `currency_conversion_rate` - Cost fields
- `credits` - JSON array of credits
- `invoice.month` - Critical for crossover data (YYYYMM format)
- `cost_type` - regular, tax, adjustment, rounding_error

### **GCP vs AWS/Azure Differences**

| Aspect             | AWS CUR                 | Azure Cost Export      | GCP BigQuery Export                    |
| ------------------ | ----------------------- | ---------------------- | -------------------------------------- |
| **Data Source**    | S3 CSV files            | Blob Storage CSV files | **BigQuery table**                     |
| **Access Method**  | Download files          | Download files         | **SQL queries**                        |
| **File Format**    | Gzip CSV                | CSV/Gzip               | **No files - query results**           |
| **Manifest**       | Required                | Optional               | **Not applicable**                     |
| **Column Format**  | `bill/PayerAccountId`   | `BillingAccountId`     | `billing_account_id` (dot notation)    |
| **Date Column**    | `identity/TimeInterval` | `Date`                 | `usage_start_time`                     |
| **Partitioning**   | By date in S3 path      | By date in path        | `_PARTITIONTIME`                       |
| **Invoice Period** | N/A                     | Billing period         | `invoice.month` (critical!)            |
| **Credits**        | N/A                     | N/A                    | JSON array                             |
| **Labels**         | Tags (flat)             | Tags (JSON)            | `labels` + `system_labels` (both JSON) |

**Key Insight:** GCP's `invoice.month` is critical - it can differ from the usage date due to late adjustments, corrections, or refunds. This causes "crossover data" where usage from one month appears in a different invoice month.

---

## **Processing Pipeline: Step-by-Step**

### **Phase 1: BigQuery Discovery & Querying**

#### **1.1 Scan Range Determination**

Unlike AWS/Azure (which process fixed monthly reports), GCP checks for **new/updated data daily**.

**Implementation:** See [`scan_start`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L184-L200) and [`scan_end`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L202-L204) properties in `gcp_report_downloader.py`

**Logic:**
- **Established providers:** Check last 10 days for updates
- **New providers:** Initial ingest of `INITIAL_INGEST_NUM_MONTHS` (default: 2 months)
- **Scan end:** Always today's date

**Why Different from AWS/Azure?**
- BigQuery receives **continuous updates** (not monthly batch files)
- Data can be corrected/adjusted retroactively
- Need to check for **changes** in already-processed dates
- Credits and adjustments can appear days/weeks after original usage

#### **1.2 Partition-to-Export Mapping**

**The Problem:** How do we know if data for a specific date has changed since we last processed it?

**The Solution:** Track the `export_time` for each partition date.

**Implementation:** See [`bigquery_export_to_partition_mapping()`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L238-L270) in `gcp_report_downloader.py`

**Process:**
1. Query BigQuery for `max(export_time)` per partition date
2. Return mapping: `{partition_date: export_time}`
3. Compare with stored export times to detect changes

**Example Output:**
```python
{
    datetime.date(2025, 1, 18): datetime(2025, 1, 19, 2, 30, 0, tzinfo=UTC),
    datetime.date(2025, 1, 19): datetime(2025, 1, 20, 2, 15, 0, tzinfo=UTC),
    datetime.date(2025, 1, 20): datetime(2025, 1, 21, 2, 45, 0, tzinfo=UTC),
}
```

#### **1.3 Manifest Collection (Pseudo-Manifests)**

Since GCP doesn't have traditional manifest files, Koku creates **pseudo-manifests**.

**Implementation:** See [`collect_new_manifests()`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L272-L300) in `gcp_report_downloader.py`

**Process:**
1. Compare BigQuery `export_time` with stored manifest `export_time`
2. If different (or missing), create a pseudo-manifest
3. Each pseudo-manifest contains `assembly_id`, `bill_date`, and `files` list
4. Triggers download/processing for that partition date

**How It Works:**
1. Query BigQuery for latest `export_time` per partition
2. Compare with stored `export_time` in Koku's database
3. If different (or missing), create a pseudo-manifest
4. Each pseudo-manifest triggers download/processing of that date's data

**Example Scenario:**
```
Day 1: Process 2025-01-15 (export_time: 2025-01-16 02:00:00)
Day 5: GCP adds credit to 2025-01-15 (export_time: 2025-01-20 03:15:00)
Day 5: Koku detects export_time change → creates new manifest → reprocesses 2025-01-15
```

#### **1.4 BigQuery Data Extraction**

**"Downloading" from BigQuery = Executing SQL Query**

**Implementation:** See [`download_file()`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L433-L504) and [`build_query_select_statement()`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L423-L431) in `gcp_report_downloader.py`

**Process:**
1. Extract partition date from filename key
2. Build SELECT query with all columns from `GCP_COLUMN_LIST`
3. Convert JSON columns (`labels`, `system_labels`, `credits`) to strings using `TO_JSON_STRING()`
4. Query BigQuery: `SELECT ... FROM table WHERE DATE(_PARTITIONTIME) = 'date'`
5. Process results in batches of `PARQUET_PROCESSING_BATCH_SIZE` (200,000 rows)
6. Write each batch to local CSV file
7. Call `create_daily_archives()` to split by invoice month and partition date

**Batching:**
- BigQuery can return millions of rows
- Process in chunks: `PARQUET_PROCESSING_BATCH_SIZE` (200,000 rows)
- Write multiple CSV files per partition date
- Files named: `{invoice_month}_{partition_date}_{batch_num}.csv`

---

### **Phase 2: Daily Archive Creation**

#### **2.1 CSV Splitting by Invoice Month & Partition Date**

**GCP's Unique Challenge: Crossover Data**

**What is Crossover Data?**
- Usage from one month can appear in a different `invoice.month`
- Example: January 31 usage might be in February's invoice due to processing delays
- Or: Credit applied in March for January usage (appears in March invoice)

**Implementation:** See [`create_daily_archives()`](../../koku/masu/external/downloader/gcp/gcp_report_downloader.py#L62-L139) in `gcp_report_downloader.py`

**Processing Flow:**
1. Read CSV files from BigQuery query results
2. Ensure label columns exist (may be missing)
3. Group data by `invoice.month` (critical for crossover!)
4. Further split by `partition_date` within each invoice month
5. Determine S3 path based on `invoice_month` (not usage date!)
6. Write CSV file: `{invoice_month}_{partition_date}_{batch}.csv`
7. Upload to S3 under invoice month folder

**Output Structure:**
```
org1234567/gcp/csv/
├── 202501/  # Invoice month folder
│   ├── 202501_2025-01-01_batch_0.csv
│   ├── 202501_2025-01-02_batch_0.csv
│   ├── 202501_2025-01-31_batch_0.csv
│   └── 202502_2025-02-01_batch_0.csv  # Crossover! Feb usage in Jan invoice
└── 202502/  # Invoice month folder
    ├── 202502_2025-02-01_batch_0.csv
    ├── 202502_2025-02-02_batch_0.csv
    └── 202501_2025-01-31_batch_0.csv  # Crossover! Jan credit in Feb invoice
```

**Why This Matters:**
- S3 path is determined by `invoice_month`, not `usage_start_time`
- Files are organized by the invoice they belong to
- Enables proper cost attribution to correct billing period

#### **2.2 Label Column Addition**

GCP labels are optional - ensure columns always exist to prevent processing errors.

**Implementation:** See [`add_label_columns()`](../../koku/masu/util/gcp/common.py#L98-L112) in `masu/util/gcp/common.py`

**Purpose:** Add empty `labels` and `system_labels` columns if they don't exist in the DataFrame.

---

### **Phase 3: Parquet Conversion**

#### **3.1 CSV to Parquet Transformation**

**Implementation:** See [`GCPReportParquetProcessor`](../../koku/masu/processor/gcp/gcp_report_parquet_processor.py#L19-L50) in `gcp_report_parquet_processor.py`

**GCP-Specific Type Handling:**
- **Numeric columns:** `cost`, `currency_conversion_rate`, `usage_amount`, `credit_amount`
- **Date columns:** `usage_start_time`, `usage_end_time`, `export_time`, `partition_time`
- **Boolean columns:** `ocp_matched` (for OpenShift correlation)
- **Table selection:** Based on S3 path (line items vs. daily vs. OCP-on-GCP)

#### **3.2 Trino Table Structure**

Trino reads Parquet files from S3 as an external table partitioned by `source`, `year`, and `month`.

**Key Columns:**
- **Billing & Project:** `billing_account_id`, `project_id`, `project_name`, `project_labels`, `project_ancestry_numbers`
- **Service & SKU:** `service_id`, `service_description`, `sku_id`, `sku_description`
- **Timestamps:** `usage_start_time`, `usage_end_time`, `export_time`
- **Labels:** `labels`, `system_labels` (JSON strings)
- **Location:** `location_location`, `location_country`, `location_region`, `location_zone`
- **Cost:** `cost`, `currency`, `currency_conversion_rate`
- **Usage:** `usage_amount`, `usage_unit`, `usage_amount_in_pricing_units`, `usage_pricing_unit`
- **Credits:** `credits` (JSON array as string)
- **Invoice:** `invoice_month` ("202501"), `cost_type` ("regular", "tax", "adjustment", "rounding_error")
- **Resources:** `resource_name`, `resource_global_name`
- **Partitions:** `partition_date`, `source`, `year`, `month`

**Partitioning:** `ARRAY['source', 'year', 'month']` enables efficient filtering and crossover data handling.

**Partition Structure:**
```
org1234567/gcp/parquet/
├── source=abc-123-uuid/
│   ├── year=2025/
│   │   ├── month=01/
│   │   │   ├── invoice_202501_date_2025-01-01.parquet
│   │   │   ├── invoice_202501_date_2025-01-02.parquet
│   │   │   └── invoice_202502_date_2025-02-01.parquet  # Crossover
│   │   └── month=02/
│   └── year=2024/
```

---

### **Phase 4: Summarization with Trino SQL**

#### **4.1 Invoice Month Date Range Discovery**

**The Challenge:** GCP invoices can contain data spanning multiple months due to crossover.

**The Solution:** Dynamically determine date range from data.

**Implementation:** See [`get_invoice_month_dates.sql`](../../koku/masu/database/trino_sql/gcp/get_invoice_month_dates.sql) in `trino_sql/gcp/`

**Query Logic:**
1. Find `min(usage_start_time)` and `max(usage_start_time)` for a specific invoice month
2. Extend date range at month boundaries (±3 days) to catch crossover data
3. Filter by `invoice_month` to get only data for that specific invoice
4. Scan multiple year/month partitions (current, previous, next) to find all relevant data

**Example:**
```python
# Processing invoice "202501" (January 2025)
# Query finds:
#   min(usage_start_time) = 2024-12-30  # Credit from previous month
#   max(usage_start_time) = 2025-02-02  # Usage from next month

# Koku will then summarize ALL this data under invoice 202501
```

#### **4.2 Daily Summary Table Population**

**Implementation:** See [`update_summary_tables()`](../../koku/masu/processor/gcp/gcp_report_parquet_summary_updater.py#L43-L118) in `gcp_report_parquet_summary_updater.py`

**Process Flow:**
1. **Get cost model markup** from database
2. **Handle table partitions** for UI summary tables
3. **Fetch invoice dates** using `get_invoice_month_dates.sql` to determine actual date range
4. **Get billing records** for the invoice month
5. **Process in chunks** (5-day increments via `TRINO_DATE_STEP`):
   - **DELETE** existing summary data for date range
   - **INSERT** new summary data via Trino SQL query
   - **Populate UI summary tables** (cost summary, service summary)
   - **Populate GCP topology** (project hierarchy)
6. **Populate tag summaries** across all dates
7. **Apply tag mappings** to daily summary
8. **Update bill timestamps** with current processing time

#### **4.3 Trino SQL Query**

**Implementation:** See [`reporting_gcpcostentrylineitem_daily_summary.sql`](../../koku/masu/database/trino_sql/gcp/reporting_gcpcostentrylineitem_daily_summary.sql) in `trino_sql/gcp/`

**Query Structure:**
1. **CTE for enabled tags:** Query PostgreSQL for enabled tag keys
2. **SELECT aggregated data:**
   - Billing account, project details
   - Service and SKU information
   - Daily date aggregation (`date(usage_start_time)`)
   - Location (region)
   - Instance type extracted from `system_labels` JSON
   - Usage amount and unit
   - Tags filtered to enabled keys only
   - Cost with markup calculation
   - Credits extracted from JSON array
3. **WHERE clause:**
   - Filter by `source_uuid` and `invoice_month`
   - Scan multiple year/month partitions for crossover data
   - Filter to date range
4. **GROUP BY:** Daily aggregation by account, project, service, SKU, date, region, instance type, cost type

**GCP-Specific Handling:**

1. **Instance Type Extraction:** Parse `system_labels` JSON to extract `compute.googleapis.com/machine_spec` field
2. **Credits Processing:** Extract amount from credits JSON array (`[{"amount": -5.23, "name": "..."}]`) and sum, with precision handling (multiply/divide by 1000000)
3. **Multi-Partition Scan:**
   - Scans current month partition
   - Scans previous month partition (for late crossover data)
   - Scans next month partition (for early crossover data)

4. **Invoice Month Filter:**
   - Critical: `WHERE invoice_month = '{{invoice_month}}'`
   - Ensures only data for specific invoice is summarized
   - Handles crossover data correctly

---

### **Phase 5: Database Storage**

#### **5.1 PostgreSQL Summary Table**

**Implementation:** See [`GCPCostEntryLineItemDailySummary`](../../koku/reporting/provider/gcp/models.py#L57-L111) model in `reporting/provider/gcp/models.py`

**Table:** `reporting_gcpcostentrylineitem_daily_summary`

**Partitioning:** RANGE partitioned by `usage_start` date

**Key Fields:**
- **IDs:** `uuid` (PK), `cost_entry_bill` (FK)
- **Billing:** `account_id` (billing_account_id)
- **Project:** `project_id`, `project_name`
- **Service:** `service_id`, `service_alias`, `sku_id`, `sku_alias`
- **Dates:** `usage_start`, `usage_end`
- **Location:** `region`, `instance_type`
- **Usage:** `unit`, `usage_amount`
- **Cost:** `line_item_type`, `unblended_cost`, `markup_cost`, `currency`
- **Credits:** `credit_amount`
- **Invoice:** `invoice_month` ("202501")
- **Metadata:** `tags` (JSON), `source_uuid`

#### **5.2 Indexes**

**Implementation:** See [model indexes](../../koku/reporting/provider/gcp/models.py#L75-L83)

**Indexes created:**
- `usage_start` - Date range queries
- `instance_type` - Instance filtering
- `tags` - GIN index for JSON tag queries
- `project_id`, `project_name` - Project filtering
- `service_id`, `service_alias` - Service filtering

---

## **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│  GCP BigQuery Table (Customer Project)                     │
│  project.dataset.billing_export                             │
│  ├── Partitioned by _PARTITIONTIME                          │
│  ├── Continuous updates (hourly/daily)                      │
│  ├── Columns: service, project, cost, credits, labels...   │
│  └── invoice.month determines billing period                │
└────────────────┬────────────────────────────────────────────┘
                 │ 1. Query partition metadata
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Download Worker (BigQuery Client)                    │
│  ├── Query: SELECT DATE(_PARTITIONTIME), MAX(export_time)  │
│  ├── Compare with stored export_times in DB                 │
│  ├── Detect new/updated partitions                          │
│  └── Create pseudo-manifests for changed partitions         │
└────────────────┬────────────────────────────────────────────┘
                 │ 2. Execute BigQuery SQL
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  BigQuery Data Extraction                                   │
│  SELECT billing_account_id, service, project, cost,         │
│         labels, credits, invoice.month, ...                 │
│  FROM `project.dataset.billing_export`                      │
│  WHERE DATE(_PARTITIONTIME) = '2025-01-15'                  │
│  ├── Process in batches (200k rows)                         │
│  ├── Write to CSV files locally                             │
│  └── Files: 202501_2025-01-15_0.csv, _1.csv, _2.csv...     │
└────────────────┬────────────────────────────────────────────┘
                 │ 3. Split by invoice month & partition date
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  CSV Daily Archives (MinIO/S3)                             │
│  org1234567/gcp/csv/                                        │
│  ├── 202501_2025-01-01_batch_0.csv                          │
│  ├── 202501_2025-01-15_batch_0.csv                          │
│  ├── 202501_2025-01-15_batch_1.csv                          │
│  ├── 202502_2025-02-01_batch_0.csv ← Crossover data!       │
│  └── 202501_2024-12-31_batch_0.csv ← Credit from prev month│
└────────────────┬────────────────────────────────────────────┘
                 │ 4. Convert to Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Parquet Processor                                     │
│  ├── Read CSV chunks (200k rows)                            │
│  ├── Apply type conversions (dates, decimals, booleans)     │
│  ├── Ensure label columns exist                             │
│  ├── Write Parquet files                                    │
│  └── Upload with partition metadata                         │
└────────────────┬────────────────────────────────────────────┘
                 │ 5. Store Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - Parquet Storage                                 │
│  org1234567/gcp/parquet/                                    │
│  └── source=abc-123/                                        │
│      └── year=2025/                                         │
│          └── month=01/                                      │
│              ├── invoice_202501_date_2025-01-01.parquet     │
│              ├── invoice_202501_date_2025-01-15.parquet     │
│              └── invoice_202502_date_2025-02-01.parquet     │
└────────────────┬────────────────────────────────────────────┘
                 │ 6. Summarize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Trino Query Engine                                         │
│  ├── Step 1: Determine invoice month date range             │
│  │   SELECT min(usage_start), max(usage_start)             │
│  │   WHERE invoice_month = '202501'                         │
│  │   Result: 2024-12-30 to 2025-02-02 (crossover!)         │
│  ├── Step 2: Scan multiple partitions for crossover data    │
│  │   WHERE year IN ('2024', '2025')                         │
│  │   AND month IN ('12', '01', '02')                        │
│  ├── Step 3: GROUP BY date, project, service, tags          │
│  │   - Aggregate cost, usage, credits                       │
│  │   - Extract instance_type from system_labels JSON        │
│  │   - Filter tags to enabled keys only                     │
│  ├── Step 4: INSERT INTO PostgreSQL                         │
│  │   - 5M line items → 50k summary rows                     │
│  └── Multi-million row aggregation in minutes               │
└────────────────┬────────────────────────────────────────────┘
                 │ 7. Store Summary
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                        │
│  org1234567 schema                                          │
│  ├── reporting_gcpcostentrylineitem_daily_summary           │
│  │   ├── 2025_01 partition                                  │
│  │   │   - Includes crossover data (Dec 30, Feb 1-2)       │
│  │   │   - All attributed to invoice 202501                 │
│  │   │   - Credits properly aggregated                      │
│  │   └── 2025_02 partition                                  │
│  ├── reporting_gcp_cost_summary (UI table)                  │
│  └── reporting_gcptags_summary                              │
└────────────────┬────────────────────────────────────────────┘
                 │ 8. API Queries
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Koku API (Django)                                          │
│  GET /api/cost-management/v1/reports/gcp/costs/             │
│  ├── Query daily_summary table                              │
│  ├── Filter by invoice_month for accurate billing period    │
│  ├── Apply filters, grouping, ordering                      │
│  ├── Cache results in Redis                                 │
│  └── Return JSON response with credits, tags, topology      │
└─────────────────────────────────────────────────────────────┘
```

---

## **Performance Characteristics**

### **Processing Metrics**

| Metric                     | Typical Value  | Notes                          |
| -------------------------- | -------------- | ------------------------------ |
| **BigQuery Query Time**    | 30-120 seconds | Depends on data volume         |
| **Line Items per Day**     | 50K - 500K     | Per partition                  |
| **Line Items per Invoice** | 1M - 10M       | Including crossover            |
| **Summary Rows**           | 10K - 100K     | ~100x reduction                |
| **BigQuery Data Extract**  | 5-15 minutes   | Query + CSV write              |
| **CSV Splitting**          | 3-10 minutes   | Pandas groupby invoice + date  |
| **Parquet Conversion**     | 8-20 minutes   | Type conversion                |
| **Trino Summarization**    | 3-12 minutes   | Multi-partition scan           |
| **Total Pipeline**         | 25-70 minutes  | For daily update (1 partition) |
| **Initial Ingest**         | 2-6 hours      | For 2 months of data           |

### **BigQuery Costs**

GCP charges for BigQuery queries:
- **Query Cost:** ~$5/TB scanned
- **Typical Daily Query:** 100MB - 1GB
- **Monthly Query Cost:** $0.50 - $5.00
- **Optimization:** Partition pruning reduces costs significantly

---

## **GCP-Specific Challenges & Solutions**

### **Challenge 1: Crossover Data (Invoice Month ≠ Usage Date)**

**Problem:** Usage from one month can appear in a different invoice month

**Real-World Examples:**
```
Scenario 1: Late usage reporting
- Usage Date: 2025-01-31
- Processed Date: 2025-02-02
- invoice.month: "202502" (February)
→ January usage appears in February invoice

Scenario 2: Credit application
- Original Usage: 2025-01-15
- Credit Applied: 2025-02-10
- invoice.month: "202502" (February)
→ January credit appears in February invoice

Scenario 3: Invoice corrections
- Original Usage: 2024-12-30
- Correction: 2025-01-05
- invoice.month: "202501" (January)
→ December usage appears in January invoice
```

**Solution:**
1. **Group by invoice_month during CSV splitting** - Process data separately for each invoice month
2. **Store in S3 paths by invoice month** - Organize files under the invoice month folder, not usage date
3. **Query extends date range at month boundaries** - Find actual min/max dates for an invoice month (e.g., invoice 202501 might span 2024-12-29 to 2025-02-03)
4. **Trino scans multiple partitions** - Check year/month partitions for previous, current, and next months while filtering to specific invoice_month

### **Challenge 2: No Traditional Manifest Files**

**Problem:** BigQuery doesn't provide manifest files listing available data

**Solution: Pseudo-Manifests based on export_time**
- Track when each partition was last exported (query BigQuery for max export_time per partition)
- Compare with stored export_times in Koku database
- If different, create a pseudo-manifest with `assembly_id`, `bill_date`, and `files` list
- This triggers reprocessing of changed partitions

### **Challenge 3: BigQuery Query Performance**

**Problem:** Scanning entire table is expensive and slow

**Solution: Partition Pruning**

Always filter by `DATE(_PARTITIONTIME)` in BigQuery queries to enable partition pruning.

**Example:** `WHERE DATE(_PARTITIONTIME) = '2025-01-15' AND usage_start_time >= '2025-01-15'`

**Benefits:**
- Only scans 1 day's partition instead of entire table
- Reduces query time from minutes to seconds
- Reduces BigQuery costs by ~100x

### **Challenge 4: Credits as JSON Array**

**Problem:** Credits are stored as JSON array, not simple column

**Format:**
```json
[
  {"name": "Committed use discount", "amount": -5.23},
  {"name": "Sustained use discount", "amount": -2.15}
]
```

**Solution:**

Extract credit amount from JSON array using `json_extract_scalar(json_parse(credits), '$["amount"]')`, cast to decimal, and sum. The multiply/divide by 1000000 pattern is used for Trino decimal precision handling.

**Why Multiply/Divide by 1000000?**
- Trino decimal precision handling
- Prevents rounding errors in aggregation
- Ensures accurate credit totals

### **Challenge 5: Instance Type in System Labels**

**Problem:** Instance type buried in system_labels JSON

**Format:**
```json
{
  "compute.googleapis.com/machine_spec": "n1-standard-4",
  "goog-gke-node": "pool-1"
}
```

**Solution:**

Extract instance type using `json_extract_scalar(json_parse(system_labels), '$["compute.googleapis.com/machine_spec"]')`

### **Challenge 6: Multiple Year/Month Partitions for Single Invoice**

**Problem:** Crossover data requires scanning multiple Parquet partitions

**Example:**
```
Invoice 202501 (January 2025) contains:
- 2024/12 partition (late December data)
- 2025/01 partition (January data)
- 2025/02 partition (early February data)
```

**Solution:**

Query multiple year/month partitions (previous, current, next) while filtering by `invoice_month` to capture all crossover data for a specific invoice.

---

## **Error Handling & Recovery**

### **Common Issues**

1. **BigQuery Authentication Errors** - Catch `GoogleCloudError` and raise `GCPReportDownloaderError`
2. **Table Not Found** - Validate table exists during provider setup via `GCPProvider().cost_usage_source_is_reachable()`
3. **Null Invoice Months** - Skip bad ingress reports with `pd.isna(invoice_month)` check
4. **Empty Query Results** - Check if `bigquery_mappings` is empty and log appropriately
5. **CSV Write Errors** - Catch `OSError` during file writing and raise `GCPReportDownloaderError`

### **Recovery Mechanisms**

- **Celery Retries:** Tasks retry on transient BigQuery errors
- **Export Time Tracking:** Detect data changes and reprocess
- **Idempotent Summarization:** DELETE + INSERT pattern
- **Manifest State:** Database tracks processing state per partition

---

## **Key Takeaways**

### **Design Principles**

1. **Query-First Architecture:** Query BigQuery directly instead of file downloads
2. **Export Time Tracking:** Detect data changes via `export_time` comparison
3. **Invoice Month Organization:** Group by `invoice.month`, not usage date
4. **Crossover Data Handling:** Extend date ranges and scan multiple partitions
5. **Partition Pruning:** Optimize BigQuery queries for performance and cost

### **Why This Architecture?**

- **Real-Time Updates:** Detect BigQuery changes within hours
- **Cost Efficiency:** Partition pruning reduces BigQuery costs 100x
- **Accuracy:** Crossover data properly attributed to correct invoice
- **Scalability:** Handle millions of line items per invoice
- **Flexibility:** Adapt to GCP's continuous export model

### **GCP vs AWS/Azure Processing Differences**

| Aspect               | AWS             | Azure              | GCP                               |
| -------------------- | --------------- | ------------------ | --------------------------------- |
| **Data Source**      | S3 files        | Blob Storage files | **BigQuery table**                |
| **Discovery**        | List S3 objects | List blobs         | **Query _PARTITIONTIME**          |
| **Manifest**         | JSON file       | Optional JSON      | **Pseudo-manifest (export_time)** |
| **Access**           | Download file   | Download file      | **Execute SQL query**             |
| **Update Detection** | File timestamp  | File timestamp     | **export_time comparison**        |
| **Billing Period**   | Fixed monthly   | Fixed monthly      | **invoice.month (crossover!)**    |
| **Costs**            | S3 storage      | Blob storage       | **BigQuery query costs**          |
| **Frequency**        | Daily/monthly   | Daily/monthly      | **Continuous (hourly)**           |
| **Corrections**      | New file        | New file           | **Update in place**               |
| **Credits**          | Separate items  | Separate items     | **JSON array in same row**        |
| **Labels**           | Tags (flat)     | Tags (JSON)        | **labels + system_labels (JSON)** |

### **Trade-offs**

**Pros:**
- ✅ Real-time data updates (hours, not days)
- ✅ Automatic correction detection
- ✅ No file management overhead
- ✅ Partition pruning reduces costs
- ✅ Direct SQL queries (powerful filtering)

**Cons:**
- ❌ Complex crossover data handling
- ❌ BigQuery query costs (though minimal with optimization)
- ❌ No traditional manifests (synthetic approach)
- ❌ Multi-partition scans for invoices
- ❌ Requires BigQuery access (can't work with just files)

---

## **Related Documentation**

- [AWS CSV Processing](./csv-processing-aws.md) - File-based processing comparison
- [Azure CSV Processing](./csv-processing-azure.md) - Blob storage approach
- [Celery Tasks Architecture](./celery-tasks.md)
- [API Serializers and Provider Maps](./api-serializers-provider-maps.md)
- [Sources and Data Ingestion](./sources-and-data-ingestion.md)

---

## **Document Version**

- **Last Updated**: 2025-10-21
- **Koku Version**: Current
- **Author**: Architecture Documentation
