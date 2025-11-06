# Deep Dive: AWS CSV File Processing in Koku

## **Overview**

Koku processes AWS Cost and Usage Reports (CUR) through a multi-stage pipeline that downloads compressed CSV files from S3, splits them into daily archives, converts them to Parquet format, and summarizes the data using Trino SQL for fast querying. This process handles millions of line items efficiently.

---

## **AWS Cost and Usage Report Structure**

### **Report Format**
- **Delivery:** AWS generates CUR files in customer S3 buckets
- **Format:** Gzip-compressed CSV files (`.csv.gz`)
- **Organization:** Monthly reports with manifest files
- **Manifest:** JSON file describing report structure and file locations

### **Key CSV Columns (100+ columns)**
```python
# Core identification columns
bill/PayerAccountId
bill/BillingPeriodStartDate
bill/BillingPeriodEndDate
bill/InvoiceId
identity/TimeInterval          # Date/time range for this line item

# Usage details
lineItem/UsageAccountId
lineItem/UsageStartDate
lineItem/UsageEndDate
lineItem/ProductCode
lineItem/ResourceId
lineItem/UsageAmount
lineItem/AvailabilityZone

# Cost columns
lineItem/UnblendedCost
lineItem/UnblendedRate
lineItem/BlendedCost
lineItem/BlendedRate
savingsPlan/SavingsPlanEffectiveCost
pricing/publicOnDemandCost

# Resource details
product/region
product/instanceType
product/productFamily
resourceTags                    # JSON string of tags
costCategory                    # JSON string of cost categories
```

---

## **Processing Pipeline: Step-by-Step**

### **Phase 1: Download & Discovery**

#### **1.1 Manifest Discovery**
**File:** `aws_report_downloader.py`

```python
# Flow: get_manifest_context_for_date()
1. Connect to AWS using IAM role assumption
2. Query Cost and Usage Report API for report definitions
3. Download manifest file from S3:
   {prefix}/{report_name}/{YYYYMMDD-YYYYMMDD}/{report_name}-Manifest.json

# Manifest structure:
{
  "assemblyId": "abc123-...",
  "billingPeriod": {"start": "20250101T000000.000Z"},
  "reportKeys": [
    "path/to/file-00001.csv.gz",
    "path/to/file-00002.csv.gz"
  ]
}
```

**Implementation:** See [`koku/masu/external/downloader/aws/aws_report_downloader.py`](../../koku/masu/external/downloader/aws/aws_report_downloader.py) - `get_manifest_context_for_date()` method

#### **1.2 File Download**

**Implementation:** See [`koku/masu/external/downloader/aws/aws_report_downloader.py`](../../koku/masu/external/downloader/aws/aws_report_downloader.py) - `download_file()` and `_check_size()` methods

**Key operations:**
1. Check disk space availability (including decompressed size)
2. Download `.csv.gz` from S3 to local temp storage
3. Validate file via S3 ETag (skip if already downloaded)
4. Store in: `/tmp/{customer_name}/aws/{bucket}/{filename}`

**Disk Space Check:**
- Reads last 4 bytes of gzip file to get uncompressed size
- Compares against available disk space before downloading

---

### **Phase 2: Daily Archive Creation**

#### **2.1 CSV Splitting by Date**

**Implementation:** See [`koku/masu/external/downloader/aws/aws_report_downloader.py`](../../koku/masu/external/downloader/aws/aws_report_downloader.py) - `create_daily_archives()` function

**Why Split?**
- AWS CUR contains data for entire month (30-31 days)
- Single file can be 1GB+ compressed, 10GB+ uncompressed
- Daily splitting enables:
  - Incremental processing
  - Parallel processing
  - Efficient date-range queries

**How It Works:**
1. Read CSV in chunks (200,000 rows via pandas)
2. Extract dates from `identity/TimeInterval` column
3. Filter rows by date
4. Write separate daily CSV files
5. Upload to S3 immediately (streaming upload)

**Output Structure:**
```
org1234567/aws/csv/
├── 2025-01-01_manifestid-123_basefile-report_batch-0.csv
├── 2025-01-01_manifestid-123_basefile-report_batch-1.csv
├── 2025-01-02_manifestid-123_basefile-report_batch-0.csv
└── ...
```

#### **2.2 Column Selection & Optimization**

**Implementation:** See [`koku/masu/util/aws/common.py`](../../koku/masu/util/aws/common.py) - `RECOMMENDED_COLUMNS` and `OPTIONAL_COLS`

**How It Works:**
- Check first row of CSV for column format (slash vs underscore)
- AWS uses two formats:
  - `bill/PayerAccountId` (older format)
  - `bill_payer_account_id` (newer format)
- Only load columns needed for processing (saves memory)
- Optional columns loaded if present (EC2 metadata, etc.)

---

### **Phase 3: Parquet Conversion**

#### **3.1 CSV to Parquet Transformation**
**File:** `parquet_report_processor.py:convert_csv_to_parquet()`

**Why Parquet?**
- **Columnar storage:** Only read columns needed for query
- **Compression:** 10x smaller than CSV (200GB → 20GB)
- **Type safety:** Enforces data types (numeric, date, boolean)
- **Partitioning:** Efficient filtering by source/year/month
- **Trino optimization:** Native Parquet support

**Implementation:** See [`koku/masu/processor/parquet/parquet_report_processor.py`](../../koku/masu/processor/parquet/parquet_report_processor.py) - `convert_csv_to_parquet()` method

**How It Works:**
1. Read CSV column headers
2. Get data type converters (dates, decimals, etc.)
3. Process CSV in chunks (200k rows)
4. Apply transformations per chunk
5. Write Parquet files with timestamp coercion
6. Upload to S3 with manifest metadata

#### **3.2 Data Type Handling**

**Implementation:** See [`koku/masu/processor/aws/aws_report_parquet_processor.py`](../../koku/masu/processor/aws/aws_report_parquet_processor.py)

**Type Conversions:**
- Numeric columns (costs, usage amounts) → `DOUBLE` (Trino)
- Date columns (usage dates, billing periods) → `TIMESTAMP` (Trino)
- Boolean columns (resource_id_matched) → `BOOLEAN` (Trino)
- Everything else → `VARCHAR` (Trino)

#### **3.3 Trino Table Creation**

**Implementation:** See [`koku/masu/processor/parquet/report_parquet_processor_base.py`](../../koku/masu/processor/parquet/report_parquet_processor_base.py)

**Table Configuration:**
- External table pointing to S3 Parquet files
- Partitioned by `source`, `year`, `month` for efficient querying
- Column types match Parquet schema
- Format: `PARQUET`

**Partition Structure in S3:**
```
org1234567/aws/parquet/
├── source=abc-123-uuid/
│   ├── year=2025/
│   │   ├── month=01/
│   │   │   ├── file_0.parquet
│   │   │   ├── file_1.parquet
│   │   │   └── file_2.parquet
│   │   └── month=02/
│   └── year=2024/
```

---

### **Phase 4: Summarization with Trino SQL**

#### **4.1 Daily Summary Table Population**
**File:** `aws_report_parquet_summary_updater.py`

**Implementation:** See [`koku/masu/processor/aws/aws_report_parquet_summary_updater.py`](../../koku/masu/processor/aws/aws_report_parquet_summary_updater.py) - `update_summary_tables()` method

**Process:**
1. Get cost model markup (if configured)
2. Find existing billing records
3. Process in 5-day chunks (TRINO_DATE_STEP):
   - DELETE existing summary data for date range
   - INSERT new summary data via Trino query
   - Populate UI summary tables (costs by service, region, etc.)
4. Populate tag and category summaries
5. Apply tag mappings (for custom tag groupings)

#### **4.2 Trino SQL Query**

**Implementation:** See [`koku/masu/database/trino_sql/aws/reporting_awscostentrylineitem_daily_summary.sql`](../../koku/masu/database/trino_sql/aws/reporting_awscostentrylineitem_daily_summary.sql)

**Query Operations:**
1. **Aggregate raw Parquet data:**
   - Group by date, account, product, region, tags
   - Sum usage amounts and costs (unblended, blended, savings plan)
   - Calculate amortized costs (handles Savings Plans logic)
   - Track distinct resource IDs

2. **Apply transformations:**
   - Filter tags to only enabled keys using `map_filter()`
   - Apply markup costs (if configured)
   - Join account aliases and organizational units

3. **Performance optimizations:**
   - Partition pruning: `WHERE year = '2025' AND month = '01'`
   - Column-level reads (Parquet columnar format)
   - Chunked processing (5-day windows)

---

### **Phase 5: Database Storage**

#### **5.1 PostgreSQL Summary Table**

**Table:** `reporting_awscostentrylineitem_daily_summary`

**Key Fields:**
- **Identifiers:** uuid, cost_entry_bill_id, usage_account_id, source_uuid
- **Time:** usage_start, usage_end
- **Resources:** product_code, region, availability_zone, instance_type
- **Usage:** usage_amount, resource_count, resource_ids[]
- **Costs:** unblended_cost, blended_cost, savingsplan_effective_cost, calculated_amortized_cost
- **Markup:** markup_cost (all cost types)
- **Metadata:** tags (JSONB), cost_category (JSONB), account_alias_id, organizational_unit_id

**Partitioning:** Monthly partitions by `usage_start` date (e.g., `_2025_01`, `_2025_02`)

**Indexes:**
- usage_start, source_uuid, usage_account_id, product_code
- GIN index on tags (JSONB)

---

## **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│  AWS S3 Bucket (Customer)                                   │
│  ├── cost-report/                                           │
│  │   ├── 20250101-20250201/                                 │
│  │   │   ├── report-Manifest.json                           │
│  │   │   ├── report-00001.csv.gz  (10GB uncompressed)       │
│  │   │   └── report-00002.csv.gz                            │
└────────────────┬────────────────────────────────────────────┘
                 │ 1. Download
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Download Worker (/tmp/)                               │
│  ├── report-00001.csv.gz  → decompress → report-00001.csv   │
│  │   (Process with Pandas in 200k row chunks)               │
│  └── Split by date from identity/TimeInterval column        │
└────────────────┬────────────────────────────────────────────┘
                 │ 2. Create Daily Archives
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - CSV Storage                                     │
│  org1234567/aws/csv/                                        │
│  ├── 2025-01-01_manifestid-123_batch-0.csv (100MB)          │
│  ├── 2025-01-01_manifestid-123_batch-1.csv                  │
│  ├── 2025-01-02_manifestid-123_batch-0.csv                  │
│  └── ... (30 days × multiple batches)                       │
└────────────────┬────────────────────────────────────────────┘
                 │ 3. Convert to Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Parquet Processor                                     │
│  ├── Read CSV chunks (200k rows)                            │
│  ├── Apply type conversions (dates, decimals, booleans)     │
│  ├── Write Parquet files (~10MB each)                       │
│  └── Upload with partition metadata                         │
└────────────────┬────────────────────────────────────────────┘
                 │ 4. Store Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - Parquet Storage                                 │
│  org1234567/aws/parquet/                                    │
│  └── source=abc-123/                                        │
│      └── year=2025/                                         │
│          └── month=01/                                      │
│              ├── day_0.parquet (10MB, columnar)             │
│              ├── day_1.parquet                              │
│              └── ... (compressed 10x vs CSV)                │
└────────────────┬────────────────────────────────────────────┘
                 │ 5. Summarize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Trino Query Engine                                         │
│  ├── CREATE TABLE aws_line_items_daily (Hive metastore)     │
│  ├── SELECT ... FROM hive.org1234567.aws_line_items_daily   │
│  │   WHERE year='2025' AND month='01'                       │
│  │   GROUP BY date, account, product, region, tags          │
│  ├── Apply filters (partition pruning)                      │
│  ├── Read only needed columns (columnar)                    │
│  ├── Aggregate millions of rows → thousands of summary rows │
│  └── INSERT INTO postgres.reporting_*_daily_summary         │
└────────────────┬────────────────────────────────────────────┘
                 │ 6. Store Summary
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                        │
│  org1234567 schema                                          │
│  ├── reporting_awscostentrylineitem_daily_summary           │
│  │   ├── 2025_01 partition (indexed, queryable)             │
│  │   │   - 10M line items → 100k summary rows               │
│  │   │   - Aggregated by day + dimensions                   │
│  │   │   - Markup costs applied                             │
│  │   │   - Tags filtered to enabled keys only               │
│  │   └── 2025_02 partition                                  │
│  ├── reporting_aws_cost_summary (UI table)                  │
│  ├── reporting_aws_storage_summary (UI table)               │
│  └── reporting_awstags_summary                              │
└────────────────┬────────────────────────────────────────────┘
                 │ 7. API Queries
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Koku API (Django)                                          │
│  GET /api/cost-management/v1/reports/aws/costs/             │
│  ├── Query daily_summary table                              │
│  ├── Apply filters, grouping, ordering                      │
│  ├── Cache results in Redis                                 │
│  └── Return JSON response                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## **Performance Characteristics**

### **Processing Metrics**

| Metric                  | Typical Value      | Notes                     |
| ----------------------- | ------------------ | ------------------------- |
| **CSV File Size**       | 1-10 GB compressed | Per monthly file          |
| **Uncompressed CSV**    | 10-100 GB          | 10x compression ratio     |
| **Parquet Size**        | 1-10 GB            | ~10x smaller than CSV     |
| **Line Items**          | 10M - 100M         | Per month                 |
| **Summary Rows**        | 100K - 1M          | ~100x reduction           |
| **Download Time**       | 5-30 minutes       | Depends on file size      |
| **CSV Splitting**       | 10-60 minutes      | Pandas chunked processing |
| **Parquet Conversion**  | 15-45 minutes      | Type conversion overhead  |
| **Trino Summarization** | 5-20 minutes       | Distributed SQL execution |
| **Total Pipeline**      | 1-3 hours          | For monthly report        |

### **Memory Management**

**Chunked processing prevents OOM:**
- `PARQUET_PROCESSING_BATCH_SIZE = 200,000` rows (~100MB in memory)
- Traditional approach: Load 10M rows × 150 columns = 15GB RAM ❌
- Chunked approach: Load 200k rows × 150 columns = 300MB RAM ✅

### **Optimization Strategies**

1. **Incremental Processing** - Only process dates >= `process_date`, skip reprocessing completed data
2. **Parallel Execution** - Multiple files processed simultaneously, Celery workers scale horizontally
3. **Smart Column Selection** - Only load needed columns with `usecols` (saves 50%+ memory)
4. **Partition Pruning** - Trino scans only relevant partitions (`WHERE year = '2025' AND month = '01'`)
5. **Tag Filtering** - Only store enabled tags using `map_filter()` to reduce JSON size

---

## **Error Handling & Recovery**

### **Common Issues**

1. **Disk Space Exhaustion** - Check before download using `_check_size()` method
2. **Empty Files** - Skip empty dataframes during processing
3. **Malformed CSV** - Handle bad lines gracefully with `on_bad_lines="warn"`
4. **S3 Access Denied** - Raise `AWSReportDownloaderNoFileError` on AccessDenied errors
5. **Trino Query Timeout** - Process in 5-day chunks (`TRINO_DATE_STEP`), retry with exponential backoff

### **Recovery Mechanisms**

- **Celery Retries:** Tasks automatically retry on transient failures
- **ETag Checking:** Skip re-downloading unchanged files
- **Idempotent Summarization:** DELETE + INSERT pattern
- **Manifest Tracking:** Database tracks processing state per file

---

## **Key Takeaways**

### **Design Principles**

1. **Streaming Over Loading:** Process files in chunks, never load entire files into memory
2. **Columnar Storage:** Parquet enables 10x compression and column-level queries
3. **Partitioning:** Both Parquet (by source/year/month) and PostgreSQL (by date) for performance
4. **Incremental Processing:** Only process new/changed data
5. **Separation of Concerns:** Download → Split → Convert → Summarize → Store

### **Why This Architecture?**

- **Scalability:** Handle 100M+ line items per month
- **Performance:** Parquet + Trino = fast aggregations
- **Cost Efficiency:** Compressed storage, efficient queries
- **Reliability:** Chunked processing, error recovery, idempotent operations
- **Maintainability:** Clear pipeline stages, separation of concerns

### **Trade-offs**

**Pros:**
- ✅ Handles massive data volumes (100M+ rows)
- ✅ Fast queries via Parquet + Trino
- ✅ Incremental updates
- ✅ Efficient storage (10x compression)

**Cons:**
- ❌ Complex multi-stage pipeline
- ❌ Requires Trino infrastructure
- ❌ Processing latency (1-3 hours)
- ❌ Debugging across multiple systems

---

This architecture has evolved to handle real-world AWS CUR processing at scale, balancing performance, cost, and reliability requirements.
