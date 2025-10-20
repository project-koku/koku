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

**Code Reference:**
```python:438:454:koku/masu/external/downloader/aws/aws_report_downloader.py
if not key.endswith(".json"):
    file_names, date_range = create_daily_archives(
        self.tracing_id,
        self.account,
        self._provider_uuid,
        full_file_path,
        s3_filename,
        manifest_id,
        start_date,
        self.context,
        self.ingress_reports,
    )
```

#### **1.2 File Download**
**File:** `aws_report_downloader.py:download_file()`

```python
# Key operations:
1. Check disk space availability (including decompressed size)
2. Download .csv.gz from S3 to local temp storage
3. Validate file via S3 ETag (skip if already downloaded)
4. Store in: /tmp/{customer_name}/aws/{bucket}/{filename}
```

**Disk Space Calculation:**
```python:227:274:koku/masu/external/downloader/aws/aws_report_downloader.py
def _check_size(self, s3key, check_inflate=False):
    # Get compressed size
    s3fileobj = self.s3_client.get_object(Bucket=self.bucket, Key=s3key)
    size = int(s3fileobj.get("ContentLength", -1))

    free_space = shutil.disk_usage(self.download_path)[2]

    # For .gz files, read last 4 bytes to get uncompressed size
    if ext == ".gz" and check_inflate:
        resp = self.s3_client.get_object(
            Bucket=self.bucket, Key=s3key,
            Range=f"bytes={size - 4}-{size}"
        )
        isize = struct.unpack("<I", resp["Body"].read(4))[0]
```

---

### **Phase 2: Daily Archive Creation**

#### **2.1 CSV Splitting by Date**
**File:** `aws_report_downloader.py:create_daily_archives()`

**Why Split?**
- AWS CUR contains data for entire month (30-31 days)
- Single file can be 1GB+ compressed, 10GB+ uncompressed
- Daily splitting enables:
  - Incremental processing
  - Parallel processing
  - Efficient date-range queries

**Processing Flow:**
```python:124:169:koku/masu/external/downloader/aws/aws_report_downloader.py
# Read CSV in chunks using pandas
with pd.read_csv(
    local_file,
    chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE,  # 200,000 rows
    usecols=lambda x: x in use_cols,  # Only needed columns
    dtype=pd.StringDtype(storage="pyarrow"),  # PyArrow backend
) as reader:
    for i, data_frame in enumerate(reader):
        # Extract unique dates from identity/TimeInterval column
        intervals = data_frame[time_interval].unique()

        for interval in intervals:
            date = interval.split("T")[0]  # Extract YYYY-MM-DD
            csv_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

            # Filter to process_date forward (incremental processing)
            if csv_date >= process_date and csv_date <= end_date:
                dates.add(date)

        # Write daily files
        for date in dates:
            daily_data = data_frame[data_frame[time_interval].str.match(date)]
            day_file = f"{date}_manifestid-{manifest_id}_basefile-{base_name}_batch-{i}.csv"
            daily_data.to_csv(day_filepath, index=False, header=True)

            # Upload to S3 immediately
            copy_local_report_file_to_s3_bucket(...)
```

**Output Structure:**
```
org1234567/aws/csv/
├── 2025-01-01_manifestid-123_basefile-report_batch-0.csv
├── 2025-01-01_manifestid-123_basefile-report_batch-1.csv
├── 2025-01-02_manifestid-123_basefile-report_batch-0.csv
└── ...
```

#### **2.2 Column Selection & Optimization**
**File:** `masu/util/aws/common.py`

```python:35:147:koku/masu/util/aws/common.py
RECOMMENDED_COLUMNS = {
    "bill/BillingEntity",
    "bill/BillType",
    "bill/PayerAccountId",
    # ... 80+ columns
}

OPTIONAL_COLS = {
    "product/physicalCores",
    "product/instanceType",
    "product/vcpu",
    "product/memory",
    "product/operatingSystem",
}
```

**Column Detection Logic:**
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

**Conversion Process:**
```python:519:576:koku/masu/processor/parquet/parquet_report_processor.py
# Read CSV column headers first
col_names = pd.read_csv(csv_filename, nrows=0, **kwargs).columns

# Get data type converters (e.g., parse dates, convert decimals)
csv_converters, kwargs = self.post_processor.get_column_converters(col_names, kwargs)

# Process CSV in chunks
with pd.read_csv(
    csv_filename,
    converters=csv_converters,
    chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE,  # 200k rows
    **kwargs
) as reader:
    for i, data_frame in enumerate(reader):
        parquet_filename = f"{base_name}_{i}.parquet"

        # Apply transformations (dates, numerics, normalization)
        data_frame, daily_frames = self.post_processor.process_dataframe(
            data_frame, parquet_base_filename
        )

        # Write parquet with specific settings
        data_frame.to_parquet(
            file_path,
            allow_truncated_timestamps=True,
            coerce_timestamps="ms",
            index=False
        )

        # Upload to S3 with metadata
        copy_data_to_s3_bucket(
            self.tracing_id, s3_path, file_name, fin,
            metadata={"ManifestId": str(self.manifest_id)}
        )
```

#### **3.2 Data Type Handling**
**File:** `aws_report_parquet_processor.py`

```python:20:45:koku/masu/processor/aws/aws_report_parquet_processor.py
numeric_columns = [
    "lineitem_normalizationfactor",
    "lineitem_normalizedusageamount",
    "lineitem_usageamount",
    "lineitem_unblendedcost",
    "lineitem_unblendedrate",
    "lineitem_blendedcost",
    "lineitem_blendedrate",
    "savingsplan_savingsplaneffectivecost",
    "pricing_publicondemandrate",
    "pricing_publicondemandcost",
]

date_columns = [
    "lineitem_usagestartdate",
    "lineitem_usageenddate",
    "bill_billingperiodstartdate",
    "bill_billingperiodenddate",
]

boolean_columns = ["resource_id_matched"]
```

**Parquet Schema Generation:**
- Numeric → `DOUBLE` (Trino)
- Date → `TIMESTAMP` (Trino)
- Boolean → `BOOLEAN` (Trino)
- Everything else → `VARCHAR` (Trino)

#### **3.3 Trino Table Creation**
**File:** `report_parquet_processor_base.py`

```python
CREATE TABLE IF NOT EXISTS hive.org1234567.aws_line_items_daily (
    lineitem_usagestartdate timestamp,
    lineitem_usageenddate timestamp,
    lineitem_usageaccountid varchar,
    lineitem_productcode varchar,
    lineitem_usageamount double,
    lineitem_unblendedcost double,
    resourcetags varchar,
    costcategory varchar,
    -- ... 100+ columns
    source varchar,
    year varchar,
    month varchar
) WITH (
    external_location = 's3a://koku-bucket/org1234567/aws/parquet/',
    format = 'PARQUET',
    partitioned_by = ARRAY['source', 'year', 'month']
)
```

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

**Process:**
```python:48:142:koku/masu/processor/aws/aws_report_parquet_summary_updater.py
def update_summary_tables(self, start_date, end_date, **kwargs):
    # 1. Get cost model markup
    markup = cost_model_accessor.markup
    markup_value = float(markup.get("value", 0)) / 100  # 10% = 0.10

    # 2. Find existing billing records
    bills = accessor.bills_for_provider_uuid(provider_uuid, start_date)
    bill_id = bills.first().id

    # 3. Process in 5-day chunks (TRINO_DATE_STEP)
    for start, end in date_range_pair(start_date, end_date, step=5):
        # 3a. DELETE existing summary data for date range
        accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
            provider_uuid, start, end, filters={"cost_entry_bill_id": bill_id}
        )

        # 3b. INSERT new summary data via Trino
        accessor.populate_line_item_daily_summary_table_trino(
            start, end, provider_uuid, bill_id, markup_value
        )

        # 3c. Populate UI summary tables (costs by service, region, etc.)
        accessor.populate_ui_summary_tables(start, end, provider_uuid)

    # 4. Populate tag and category summaries
    accessor.populate_tags_summary_table(bill_ids, start_date, end_date)
    accessor.populate_category_summary_table(bill_ids, start_date, end_date)

    # 5. Apply tag mappings (for custom tag groupings)
    accessor.update_line_item_daily_summary_with_tag_mapping(
        start_date, end_date, bill_ids
    )
```

#### **4.2 Trino SQL Query**
**File:** `trino_sql/aws/reporting_awscostentrylineitem_daily_summary.sql`

**Query Structure:**
```sql:82:157:koku/masu/database/trino_sql/aws/reporting_awscostentrylineitem_daily_summary.sql
-- Step 1: Aggregate raw Parquet data by day
SELECT
    date(lineitem_usagestartdate) as usage_start,
    lineitem_usageaccountid as usage_account_id,
    lineitem_productcode as product_code,
    product_region as region,
    product_instancetype as instance_type,
    resourcetags as tags,

    -- Aggregate usage
    sum(CASE
        WHEN lineitem_lineitemtype='SavingsPlanNegation' THEN 0.0
        ELSE lineitem_usageamount
    END) as usage_amount,

    -- Aggregate costs
    sum(lineitem_unblendedcost) as unblended_cost,
    sum(lineitem_blendedcost) as blended_cost,
    sum(savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,

    -- Calculate amortized cost (handles Savings Plans)
    sum(CASE
        WHEN lineitem_lineitemtype IN (
            'SavingsPlanCoveredUsage', 'SavingsPlanNegation',
            'SavingsPlanUpfrontFee', 'SavingsPlanRecurringFee'
        ) THEN savingsplan_savingsplaneffectivecost
        ELSE lineitem_unblendedcost
    END) as calculated_amortized_cost,

    -- Resource tracking
    array_agg(DISTINCT lineitem_resourceid) as resource_ids,
    count(DISTINCT lineitem_resourceid) as resource_count

FROM hive.org1234567.aws_line_items_daily
WHERE source = 'abc-123-provider-uuid'
    AND year = '2025'
    AND month = '01'
    AND lineitem_usagestartdate >= TIMESTAMP '2025-01-01'
    AND lineitem_usagestartdate < TIMESTAMP '2025-01-06'

GROUP BY
    date(lineitem_usagestartdate),
    lineitem_usageaccountid,
    lineitem_productcode,
    product_region,
    resourcetags,
    product_instancetype,
    pricing_unit
```

**Step 2: Apply transformations and insert into PostgreSQL:**
```sql:37:81:koku/masu/database/trino_sql/aws/reporting_awscostentrylineitem_daily_summary.sql
-- Filter tags to only enabled keys
map_filter(
    cast(json_parse(tags) as map(varchar, varchar)),
    (k,v) -> contains(enabled_keys, k)
) as tags,

-- Apply markup costs
cast(unblended_cost * 0.10 AS decimal(24,9)) as markup_cost,
cast(blended_cost * 0.10 AS decimal(33,15)) as markup_cost_blended,

-- Join account aliases
LEFT JOIN postgres.org1234567.reporting_awsaccountalias AS aa
    ON usage_account_id = aa.account_id

-- Join organizational units
LEFT JOIN postgres.org1234567.reporting_awsorganizationalunit AS ou
    ON aa.id = ou.account_alias_id
```

**Performance Optimizations:**
- Partition pruning: `WHERE year = '2025' AND month = '01'`
- Only enabled tags extracted (map_filter)
- Distinct resource IDs tracked efficiently (array_agg)
- Chunked processing (5-day windows)

---

### **Phase 5: Database Storage**

#### **5.1 PostgreSQL Summary Table**
**Table:** `reporting_awscostentrylineitem_daily_summary`

**Structure:**
```sql
CREATE TABLE reporting_awscostentrylineitem_daily_summary (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID UNIQUE,
    cost_entry_bill_id INTEGER,
    usage_start DATE,
    usage_end DATE,
    usage_account_id VARCHAR(50),
    product_code VARCHAR,
    product_family VARCHAR,
    region VARCHAR,
    availability_zone VARCHAR(50),
    instance_type VARCHAR,

    -- Usage metrics
    usage_amount NUMERIC(24,9),
    normalization_factor NUMERIC,
    normalized_usage_amount NUMERIC(24,9),
    resource_count INTEGER,
    resource_ids TEXT[],

    -- Cost metrics
    unblended_cost NUMERIC(24,9),
    unblended_rate NUMERIC(24,9),
    blended_cost NUMERIC(24,9),
    blended_rate NUMERIC(24,9),
    savingsplan_effective_cost NUMERIC(24,9),
    calculated_amortized_cost NUMERIC(33,9),
    public_on_demand_cost NUMERIC(24,9),

    -- Markup costs
    markup_cost NUMERIC(24,9),
    markup_cost_blended NUMERIC(33,15),
    markup_cost_savingsplan NUMERIC(33,15),
    markup_cost_amortized NUMERIC(33,9),

    -- Metadata
    tags JSONB,
    cost_category JSONB,
    account_alias_id INTEGER,
    organizational_unit_id INTEGER,
    source_uuid UUID
) PARTITION BY RANGE (usage_start);
```

#### **5.2 Table Partitioning**
**Monthly partitions for efficient querying:**

```sql
-- Automatic partition creation
CREATE TABLE reporting_awscostentrylineitem_daily_summary_2025_01
    PARTITION OF reporting_awscostentrylineitem_daily_summary
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE reporting_awscostentrylineitem_daily_summary_2025_02
    PARTITION OF reporting_awscostentrylineitem_daily_summary
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
```

**Benefits:**
- Query only relevant month(s)
- Efficient partition pruning
- Easy data retention (drop old partitions)
- Parallel index creation

#### **5.3 Indexes**
```sql
CREATE INDEX idx_aws_usage_start
    ON reporting_awscostentrylineitem_daily_summary (usage_start);

CREATE INDEX idx_aws_source_uuid
    ON reporting_awscostentrylineitem_daily_summary (source_uuid);

CREATE INDEX idx_aws_account_id
    ON reporting_awscostentrylineitem_daily_summary (usage_account_id);

CREATE INDEX idx_aws_product_code
    ON reporting_awscostentrylineitem_daily_summary (product_code);

CREATE INDEX idx_aws_tags
    ON reporting_awscostentrylineitem_daily_summary USING GIN (tags);
```

---

## **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│  AWS S3 Bucket (Customer)                                   │
│  ├── cost-report/                                           │
│  │   ├── 20250101-20250201/                                │
│  │   │   ├── report-Manifest.json                          │
│  │   │   ├── report-00001.csv.gz  (10GB uncompressed)     │
│  │   │   └── report-00002.csv.gz                           │
└────────────────┬────────────────────────────────────────────┘
                 │ 1. Download
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Download Worker (/tmp/)                               │
│  ├── report-00001.csv.gz  → decompress → report-00001.csv  │
│  │   (Process with Pandas in 200k row chunks)              │
│  └── Split by date from identity/TimeInterval column       │
└────────────────┬────────────────────────────────────────────┘
                 │ 2. Create Daily Archives
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - CSV Storage                                     │
│  org1234567/aws/csv/                                        │
│  ├── 2025-01-01_manifestid-123_batch-0.csv (100MB)         │
│  ├── 2025-01-01_manifestid-123_batch-1.csv                 │
│  ├── 2025-01-02_manifestid-123_batch-0.csv                 │
│  └── ... (30 days × multiple batches)                      │
└────────────────┬────────────────────────────────────────────┘
                 │ 3. Convert to Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Parquet Processor                                     │
│  ├── Read CSV chunks (200k rows)                           │
│  ├── Apply type conversions (dates, decimals, booleans)    │
│  ├── Write Parquet files (~10MB each)                      │
│  └── Upload with partition metadata                        │
└────────────────┬────────────────────────────────────────────┘
                 │ 4. Store Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - Parquet Storage                                 │
│  org1234567/aws/parquet/                                    │
│  └── source=abc-123/                                        │
│      └── year=2025/                                         │
│          └── month=01/                                      │
│              ├── day_0.parquet (10MB, columnar)            │
│              ├── day_1.parquet                              │
│              └── ... (compressed 10x vs CSV)               │
└────────────────┬────────────────────────────────────────────┘
                 │ 5. Summarize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Trino Query Engine                                         │
│  ├── CREATE TABLE aws_line_items_daily (Hive metastore)   │
│  ├── SELECT ... FROM hive.org1234567.aws_line_items_daily  │
│  │   WHERE year='2025' AND month='01'                      │
│  │   GROUP BY date, account, product, region, tags         │
│  ├── Apply filters (partition pruning)                     │
│  ├── Read only needed columns (columnar)                   │
│  ├── Aggregate millions of rows → thousands of summary rows│
│  └── INSERT INTO postgres.reporting_*_daily_summary        │
└────────────────┬────────────────────────────────────────────┘
                 │ 6. Store Summary
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                        │
│  org1234567 schema                                          │
│  ├── reporting_awscostentrylineitem_daily_summary          │
│  │   ├── 2025_01 partition (indexed, queryable)           │
│  │   │   - 10M line items → 100k summary rows             │
│  │   │   - Aggregated by day + dimensions                 │
│  │   │   - Markup costs applied                           │
│  │   │   - Tags filtered to enabled keys only            │
│  │   └── 2025_02 partition                                 │
│  ├── reporting_aws_cost_summary (UI table)                 │
│  ├── reporting_aws_storage_summary (UI table)              │
│  └── reporting_awstags_summary                             │
└────────────────┬────────────────────────────────────────────┘
                 │ 7. API Queries
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Koku API (Django)                                          │
│  GET /api/cost-management/v1/reports/aws/costs/            │
│  ├── Query daily_summary table                             │
│  ├── Apply filters, grouping, ordering                     │
│  ├── Cache results in Redis                                │
│  └── Return JSON response                                  │
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

```python
# Chunked processing prevents OOM
PARQUET_PROCESSING_BATCH_SIZE = 200,000 rows  # ~100MB in memory

# Example: 10M row file
# Traditional: Load 10M rows × 150 columns = 15GB RAM ❌
# Chunked: Load 200k rows × 150 columns = 300MB RAM ✅
```

### **Optimization Strategies**

1. **Incremental Processing**
   - Only process dates >= `process_date`
   - Skip reprocessing completed data
   - Handle invoice corrections automatically

2. **Parallel Execution**
   - Multiple files processed simultaneously
   - Celery workers scale horizontally
   - Trino distributes query across workers

3. **Smart Column Selection**
   ```python
   # Only load needed columns (saves 50%+ memory)
   usecols=lambda x: x in RECOMMENDED_COLUMNS
   ```

4. **Partition Pruning**
   ```sql
   -- Trino only scans relevant partitions
   WHERE year = '2025' AND month = '01'
   -- Skips scanning 11 other months
   ```

5. **Tag Filtering**
   ```sql
   -- Only store enabled tags (reduces JSON size)
   map_filter(tags, (k,v) -> contains(enabled_keys, k))
   ```

---

## **Error Handling & Recovery**

### **Common Issues**

1. **Disk Space Exhaustion**
   ```python
   # Check before download
   if not self._check_size(s3key, check_inflate=True):
       raise AWSReportDownloaderError("Insufficient disk space")
   ```

2. **Empty Files**
   ```python
   # Skip empty dataframes
   if data_frame.empty:
       continue
   ```

3. **Malformed CSV**
   ```python
   # Handle bad lines gracefully
   pd.read_csv(file, on_bad_lines="warn")
   ```

4. **S3 Access Denied**
   ```python
   except ClientError as ex:
       if ex.response["Error"]["Code"] == "AccessDenied":
           raise AWSReportDownloaderNoFileError(...)
   ```

5. **Trino Query Timeout**
   - Process in 5-day chunks (`TRINO_DATE_STEP`)
   - Retry with exponential backoff
   - Monitor query queue depth

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
