# Deep Dive: Azure Cost Export Processing in Koku

## **Overview**

Koku processes Azure Cost Exports through a multi-stage pipeline that downloads CSV files from Azure Blob Storage, splits them into daily archives, converts them to Parquet format, and summarizes the data using Trino SQL for fast querying. This process efficiently handles millions of line items from Azure consumption data.

---

## **Azure Cost Export Structure**

### **Export Format**
- **Delivery:** Azure generates cost exports in customer Storage Accounts
- **Format:** CSV files (`.csv`) - typically uncompressed or gzip-compressed (`.csv.gz`)
- **Organization:** Monthly exports with optional manifest files
- **Manifest:** JSON file describing export metadata and configuration

### **Key CSV Columns (60+ columns)**
```python
# Core identification columns
BillingAccountId
BillingAccountName
BillingPeriodStartDate
BillingPeriodEndDate
Date                           # Daily date for this line item

# Subscription details
SubscriptionId
SubscriptionGuid
SubscriptionName

# Usage details
ConsumedService               # Azure service name
ResourceId                     # Unique resource identifier
ResourceLocation               # Azure region
ResourceGroup / ResourceGroupName
ResourceName
Quantity                       # Usage amount
UnitOfMeasure                  # e.g., "100 Hours", "GB-Mo"

# Cost columns
CostInBillingCurrency         # Actual cost in billing currency
BillingCurrency / BillingCurrencyCode
EffectivePrice                # Price per unit
UnitPrice                     # List price per unit
PayGPrice                     # Pay-as-you-go price

# Meter details
MeterId                       # Unique meter identifier
MeterCategory                 # High-level category (e.g., "Virtual Machines")
MeterSubCategory              # Sub-category
MeterName                     # Specific meter name
MeterRegion                   # Meter region

# Product details
ProductName
PublisherName
PublisherType
ServiceFamily
ServiceInfo1
ServiceInfo2

# Additional metadata
AdditionalInfo                # JSON string with extra metadata
Tags                          # JSON string of resource tags
OfferId
ReservationId
ReservationName
```

### **Azure vs AWS Differences**

| Aspect            | AWS CUR                              | Azure Cost Export                 |
| ----------------- | ------------------------------------ | --------------------------------- |
| **Date Column**   | `identity/TimeInterval`              | `Date`                            |
| **File Format**   | Always gzip                          | CSV or gzip optional              |
| **Column Naming** | Slash format (`bill/PayerAccountId`) | CamelCase (`BillingAccountId`)    |
| **Cost Types**    | Unblended, Blended, Amortized        | PreTax Cost (single value)        |
| **Account**       | Usage Account ID                     | Subscription GUID                 |
| **Service**       | Product Code                         | Consumed Service / Meter Category |
| **Manifest**      | Required                             | Optional                          |
| **Delivery**      | S3 Bucket                            | Blob Storage                      |

---

## **Processing Pipeline: Step-by-Step**

### **Phase 1: Download & Discovery**

#### **1.1 Export Discovery**
**File:** `azure_report_downloader.py`

```python
# Flow: get_report_path()
1. Connect to Azure using Service Principal credentials
2. Query Cost Management API for export configuration:
   - Subscription ID
   - Resource Group
   - Storage Account
   - Container Name
   - Export Name
3. Build report path:
   /{directory}/{export_name}/{YYYYMMDD-YYYYMMDD}/
```

**Azure Authentication:**
```python
service = AzureService(
    tenant_id=credentials['tenant_id'],
    client_id=credentials['client_id'],
    client_secret=credentials['client_secret'],
    resource_group_name=data_source['resource_group'],
    storage_account_name=data_source['storage_account'],
    subscription_id=credentials['subscription_id']
)
```

#### **1.2 Manifest Discovery (Optional)**
**File:** `azure_report_downloader.py:_get_manifest()`

Azure manifests are optional and may not always exist:

```python
# Manifest structure (if present):
{
  "exportName": "daily-export",
  "billingPeriod": {
    "start": "20250101",
    "end": "20250131"
  },
  "blobCount": 1,
  "blobs": [
    {
      "blobName": "export-data.csv",
      "byteCount": 123456789
    }
  ]
}
```

**Without Manifest (Ingress Reports):**
```python
# For ingress reports (direct file paths provided):
if self.ingress_reports:
    reports = [report.split(f"{container}/")[1] for report in self.ingress_reports]
    # Build manifest from provided report paths
    manifest["reportKeys"] = report_keys
    manifest["assemblyId"] = uuid.uuid4()
```

#### **1.3 File Download**
**File:** `azure_service.py:download_file()`

```python
# Key operations:
1. Get latest blob from Azure Blob Storage
2. Download CSV from container to local temp storage
3. Handle both CSV and GZIP formats
4. Store in: /tmp/{customer_name}/azure/{container}/{filename}
```

**Implementation:** See [`koku/masu/external/downloader/azure/azure_service.py`](../../koku/masu/external/downloader/azure/azure_service.py) - `download_file()` method

**How it works:**
- Get blob client from Azure Blob Storage
- Download blob to local file
- Return local file path
- Handle Azure errors gracefully

---

### **Phase 2: Daily Archive Creation**

#### **2.1 CSV Splitting by Date**
**File:** `azure_report_downloader.py:create_daily_archives()`

**Why Split?**
- Azure exports contain data for entire month (up to 31 days)
- Single file can be 500MB+ uncompressed
- Daily splitting enables:
  - Incremental processing
  - Parallel processing
  - Efficient date-range queries

**Implementation:** See [`koku/masu/external/downloader/azure/azure_report_downloader.py`](../../koku/masu/external/downloader/azure/azure_report_downloader.py) - `create_daily_archives()` function

**How it works:**
1. Determine processing start date using heuristics
2. Detect date column (`Date` in modern exports, reject legacy `UsageDateTime`)
3. Read CSV in chunks (200,000 rows via pandas)
4. Sort by date and filter to process_date forward
5. Extract unique dates and write separate daily CSV files
6. Upload to S3 immediately (streaming upload)

**Output Structure:**
```
org1234567/azure/csv/
├── 2025-01-01_manifestid-123_basefile-export_batch-0.csv
├── 2025-01-01_manifestid-123_basefile-export_batch-1.csv
├── 2025-01-02_manifestid-123_basefile-export_batch-0.csv
└── ...
```

#### **2.2 Processing Date Logic**

**Implementation:** See [`koku/masu/external/downloader/azure/azure_report_downloader.py`](../../koku/masu/external/downloader/azure/azure_report_downloader.py) - `get_processing_date()` function

Azure doesn't have an invoice finalization date, so Koku uses heuristics to determine processing start date:

**Process entire month if:**
1. Previous year (and not first day of current month)
2. Previous month (and not first day of current month)
3. Initial setup (`setup_complete=False`)
4. Ingress reports (manually uploaded)

**Otherwise:** Check for existing data in S3 and process incrementally

#### **2.3 Column Requirements**

**Implementation:** See [`koku/masu/util/azure/common.py`](../../koku/masu/util/azure/common.py) - `INGRESS_REQUIRED_COLUMNS`

**Required Columns** - Core columns including billing account, date, cost, meter details, resource info, subscriptions, and tags. Also handles alternate column names for Azure schema variations (e.g., `billingcurrencycode` vs `billingcurrency`).

---

### **Phase 3: Parquet Conversion**

#### **3.1 CSV to Parquet Transformation**
**File:** `azure_report_parquet_processor.py`

**Why Parquet?**
- **Columnar storage:** Only read columns needed for query
- **Compression:** 10x smaller than CSV
- **Type safety:** Enforces data types (numeric, date, boolean)
- **Partitioning:** Efficient filtering by source/year/month
- **Trino optimization:** Native Parquet support

**Implementation:** See [`koku/masu/processor/azure/azure_report_parquet_processor.py`](../../koku/masu/processor/azure/azure_report_parquet_processor.py)

**Azure-Specific Type Conversions:**
- **Numeric columns:** quantity, cost, prices (→ DOUBLE in Trino)
- **Date columns:** date, billing period dates (→ TIMESTAMP in Trino)
- **Boolean columns:** resource_id_matched (→ BOOLEAN in Trino)
- **Table selection:** Uses OCP-on-Azure table if OpenShift data, otherwise standard line item table

#### **3.2 Parquet Schema Generation**

**Azure Parquet Schema:**
- Numeric → `DOUBLE` (Trino)
- Date → `TIMESTAMP` (Trino)
- Boolean → `BOOLEAN` (Trino)
- Everything else → `VARCHAR` (Trino)

#### **3.3 Trino Table Creation**

```python
CREATE TABLE IF NOT EXISTS hive.org1234567.azure_line_items (
    date timestamp,
    billingperiodstartdate timestamp,
    billingperiodenddate timestamp,
    billingaccountid varchar,
    billingaccountname varchar,
    subscriptionid varchar,
    subscriptionguid varchar,
    subscriptionname varchar,
    resourcegroup varchar,
    resourcelocation varchar,
    resourceid varchar,
    resourcename varchar,
    consumedservice varchar,
    metercategory varchar,
    metersubcategory varchar,
    meterid varchar,
    metername varchar,
    meterregion varchar,
    quantity double,
    costinbillingcurrency double,
    effectiveprice double,
    unitprice double,
    billingcurrency varchar,
    billingcurrencycode varchar,
    unitofmeasure varchar,
    productname varchar,
    publishername varchar,
    publishertype varchar,
    servicefamily varchar,
    tags varchar,
    additionalinfo varchar,
    -- ... more columns
    source varchar,
    year varchar,
    month varchar
) WITH (
    external_location = 's3a://koku-bucket/org1234567/azure/parquet/',
    format = 'PARQUET',
    partitioned_by = ARRAY['source', 'year', 'month']
)
```

**Partition Structure in S3:**
```
org1234567/azure/parquet/
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
**File:** `azure_report_parquet_summary_updater.py`

**Implementation:** See [`koku/masu/processor/azure/azure_report_parquet_summary_updater.py`](../../koku/masu/processor/azure/azure_report_parquet_summary_updater.py) - `update_summary_tables()` method

**Process:**
1. Get cost model markup (if configured)
2. Handle partitions for UI summary tables
3. Get billing records
4. Process in 5-day chunks (TRINO_DATE_STEP):
   - DELETE existing summary data for date range
   - INSERT new summary data via Trino query
   - Populate UI summary tables
5. Populate tag summaries
6. Apply tag mappings
7. Update bill timestamps

#### **4.2 Trino SQL Query**
**File:** `trino_sql/azure/reporting_azurecostentrylineitem_daily_summary.sql`

**Implementation:** See [`koku/masu/database/trino_sql/azure/reporting_azurecostentrylineitem_daily_summary.sql`](../../koku/masu/database/trino_sql/azure/reporting_azurecostentrylineitem_daily_summary.sql)

**Query Operations:**
1. **Aggregate raw Parquet data:**
   - Group by date, subscription, location, service
   - Handle subscription ID/GUID variations
   - Extract instance type from JSON AdditionalInfo field
   - Normalize unit of measure (extract multipliers like "100" from "100 Hours")
   - Parse and filter tags

2. **Apply transformations:**
   - Multiply usage by unit multiplier
   - Normalize unit names ("Hours" → "Hrs", "GB/Month" → "GB-Mo")
   - Filter tags to only enabled keys
   - Apply markup costs (if configured)

3. **Performance optimizations:**
   - Partition pruning by year/month
   - Column-level reads (Parquet)
   - Chunked processing (5-day windows)

**Azure-Specific Handling:**

1. **Unit of Measure Normalization:**
   - Azure meters usage in blocks (e.g., "100 Hours")
   - Extract multiplier from UnitOfMeasure string
   - Normalize unit names ("Hours" → "Hrs", "GB/Month" → "GB-Mo")
   - Multiply usage by multiplier

2. **Subscription Handling:**
   - Use SubscriptionGuid if SubscriptionId is empty
   - Fall back through multiple name fields

3. **Service Name:**
   - Use ServiceName if available
   - Fall back to MeterCategory if ServiceName is empty

4. **Instance Type:**
   - Extracted from AdditionalInfo JSON field
   - Uses `$.ServiceType` path

**Performance Optimizations:**
- Partition pruning: `WHERE year = '2025' AND month = '01'`
- Only enabled tags extracted (map_filter)
- Distinct resource IDs tracked efficiently (array_agg)
- Chunked processing (5-day windows)

---

### **Phase 5: Database Storage**

#### **5.1 PostgreSQL Summary Table**
**Table:** `reporting_azurecostentrylineitem_daily_summary`

**Implementation:** See [`koku/reporting/provider/azure/models.py`](../../koku/reporting/provider/azure/models.py) - `AzureCostEntryLineItemDailySummary` model

**Key Fields:**
- **Identifiers:** uuid, cost_entry_bill, subscription_guid, source_uuid
- **Time:** usage_start, usage_end
- **Resources:** instance_type, service_name, resource_location
- **Usage:** usage_quantity, unit_of_measure
- **Costs:** pretax_cost, markup_cost, currency
- **Resource tracking:** instance_ids[], instance_count
- **Metadata:** tags (JSONB)

**Partitioning:** Monthly RANGE partitions by `usage_start` (e.g., `_2025_01`, `_2025_02`)

**Indexes:**
- usage_start, subscription_guid, resource_location, instance_type, subscription_name
- GIN functional index on service_name for case-insensitive partial matching

---

## **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│  Azure Blob Storage (Customer Storage Account)              │
│  ├── container-name/                                        │
│  │   ├── export-name/                                       │
│  │   │   ├── 20250101-20250131/                             │
│  │   │   │   ├── export-data.csv (500MB)                    │
│  │   │   │   └── export-manifest.json (optional)            │
└────────────────┬────────────────────────────────────────────┘
                 │ 1. Download via Azure Blob SDK
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Download Worker (/tmp/)                               │
│  ├── export-data.csv → Process with Pandas in 200k chunks   │
│  └── Split by date from "Date" column                       │
└────────────────┬────────────────────────────────────────────┘
                 │ 2. Create Daily Archives
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - CSV Storage                                     │
│  org1234567/azure/csv/                                      │
│  ├── 2025-01-01_manifestid-123_batch-0.csv (50MB)           │
│  ├── 2025-01-01_manifestid-123_batch-1.csv                  │
│  ├── 2025-01-02_manifestid-123_batch-0.csv                  │
│  └── ... (31 days × multiple batches)                       │
└────────────────┬────────────────────────────────────────────┘
                 │ 3. Convert to Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MASU Parquet Processor                                     │
│  ├── Read CSV chunks (200k rows)                            │
│  ├── Apply type conversions (dates, decimals, booleans)     │
│  ├── Normalize unit of measure                              │
│  ├── Write Parquet files (~10MB each)                       │
│  └── Upload with partition metadata                         │
└────────────────┬────────────────────────────────────────────┘
                 │ 4. Store Parquet
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  MinIO/S3 - Parquet Storage                                 │
│  org1234567/azure/parquet/                                  │
│  └── source=abc-123/                                        │
│      └── year=2025/                                         │
│          └── month=01/                                      │
│              ├── day_0.parquet (8MB, columnar)              │
│              ├── day_1.parquet                              │
│              └── ... (compressed 10x vs CSV)                │
└────────────────┬────────────────────────────────────────────┘
                 │ 5. Summarize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Trino Query Engine                                         │
│  ├── CREATE TABLE azure_line_items (Hive metastore)         │
│  ├── SELECT ... FROM hive.org1234567.azure_line_items       │
│  │   WHERE year='2025' AND month='01'                       │
│  │   GROUP BY date, subscription, service, location, tags   │
│  ├── Normalize unit of measure (100 Hours → 100 × Hrs)      │
│  ├── Extract instance type from AdditionalInfo JSON         │
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
│  ├── reporting_azurecostentrylineitem_daily_summary         │
│  │   ├── 2025_01 partition (indexed, queryable)             │
│  │   │   - 5M line items → 50k summary rows                 │
│  │   │   - Aggregated by day + dimensions                   │
│  │   │   - Markup costs applied                             │
│  │   │   - Tags filtered to enabled keys only               │
│  │   │   - Unit of measure normalized                       │
│  │   └── 2025_02 partition                                  │
│  ├── reporting_azure_cost_summary (UI table)                │
│  ├── reporting_azure_storage_summary (UI table)             │
│  └── reporting_azuretags_summary                            │
└────────────────┬────────────────────────────────────────────┘
                 │ 7. API Queries
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Koku API (Django)                                          │
│  GET /api/cost-management/v1/reports/azure/costs/           │
│  ├── Query daily_summary table                              │
│  ├── Apply filters, grouping, ordering                      │
│  ├── Cache results in Redis                                 │
│  └── Return JSON response                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## **Performance Characteristics**

### **Processing Metrics**

| Metric                  | Typical Value | Notes                     |
| ----------------------- | ------------- | ------------------------- |
| **CSV File Size**       | 100MB - 1GB   | Per monthly file          |
| **Line Items**          | 1M - 10M      | Per month                 |
| **Summary Rows**        | 10K - 100K    | ~100x reduction           |
| **Download Time**       | 2-10 minutes  | Depends on file size      |
| **CSV Splitting**       | 5-20 minutes  | Pandas chunked processing |
| **Parquet Conversion**  | 10-30 minutes | Type conversion overhead  |
| **Trino Summarization** | 3-15 minutes  | Distributed SQL execution |
| **Total Pipeline**      | 30-90 minutes | For monthly report        |

### **Memory Management**

```python
# Chunked processing prevents OOM
PARQUET_PROCESSING_BATCH_SIZE = 200,000 rows  # ~80MB in memory

# Example: 5M row file
# Traditional: Load 5M rows × 60 columns = 6GB RAM ❌
# Chunked: Load 200k rows × 60 columns = 240MB RAM ✅
```

### **Optimization Strategies**

1. **Incremental Processing**
   - Determine process_date based on month/year logic
   - Skip reprocessing completed data
   - Handle late-arriving data

2. **Unit of Measure Normalization**
   ```python
   # Azure meters in blocks: "100 Hours"
   # Extract multiplier: 100
   # Normalize unit: "Hrs"
   # Multiply usage: quantity * 100
   ```

3. **Smart Column Selection**
   ```python
   # Azure has ~60 columns (vs AWS ~150)
   # Still use column filtering for efficiency
   usecols=lambda x: x in INGRESS_REQUIRED_COLUMNS
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

## **Azure-Specific Challenges & Solutions**

### **Challenge 1: Variable Unit of Measure**

**Problem:** Azure meters usage in variable blocks (e.g., "100 Hours", "10000 GB/Month")

**Solution:**
```sql
-- Extract multiplier from UnitOfMeasure
CASE
    WHEN regexp_like(split_part(unitofmeasure, ' ', 1), '^\d+(\.\d+)?$')
    THEN cast(split_part(unitofmeasure, ' ', 1) as INTEGER)
    ELSE 1
END as multiplier

-- Normalize unit name
CASE
    WHEN split_part(unitofmeasure, ' ', 2) IN ('Hours', 'Hour')
        THEN 'Hrs'
    WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
        THEN 'GB-Mo'
    ELSE unitofmeasure
END as unit_of_measure

-- Apply multiplier to usage
sum(usage_quantity * multiplier) AS usage_quantity
```

### **Challenge 2: Multiple Column Name Variations**

**Problem:** Azure schemas have evolved over time with different column names

**Solution:**
```python
# Support multiple column name variations
INGRESS_REQUIRED_ALT_COLUMNS = [
    ["billingcurrencycode", "billingcurrency"],
    ["resourcegroup", "resourcegroupname"]
]

# In SQL: Use COALESCE to handle variations
coalesce(nullif(billingcurrencycode, ''), billingcurrency) as currency
coalesce(nullif(servicename, ''), metercategory) as service_name
```

### **Challenge 3: No Invoice Finalization Date**

**Problem:** Azure doesn't provide an invoice finalization marker like AWS

**Solution:**
```python
# Use heuristics based on date and month
if (
    start_date.year < dh.today.year and dh.today.day > 1
    or start_date.month < dh.today.month and dh.today.day > 1
):
    # Process entire month (historical data)
    process_date = start_date
else:
    # Current month: check for existing data
    process_date = get_or_clear_daily_s3_by_date(...)
```

### **Challenge 4: Optional Manifest**

**Problem:** Azure manifests are optional and may not exist

**Solution:**
```python
# Build synthetic manifest from blob listing
if not manifest:
    blobs = list_blobs(report_path, container_name)
    latest_blob = get_latest_blob(blobs)
    manifest = {
        "assemblyId": uuid.uuid4(),
        "reportKeys": [latest_blob.name],
        "billingPeriod": derive_from_path(report_path)
    }
```

### **Challenge 5: Instance Type in JSON**

**Problem:** Instance type buried in AdditionalInfo JSON field

**Solution:**
```sql
-- Extract from JSON in Trino
json_extract_scalar(json_parse(additionalinfo), '$.ServiceType') as instance_type
```

---

## **Error Handling & Recovery**

### **Common Issues**

1. **Authentication Errors**
   ```python
   except ClientAuthenticationError as error:
       raise AzureServiceError(f"Failed to authenticate: {error}")
   ```

2. **Container Not Found**
   ```python
   except ResourceNotFoundError:
       message = f"Container {container_name} does not exist"
       raise AzureCostReportNotFound(message)
   ```

3. **Authorization Issues**
   ```python
   except HttpResponseError as httpError:
       if httpError.status_code == 403:
           message = "Authorization error accessing storage account"
   ```

4. **Legacy Schema Detection**
   ```python
   if time_interval not in ["Date", "date"]:
       LOG.warning("Legacy Azure schema detected with UsageDateTime")
       return [], {}  # Skip processing
   ```

5. **Empty Files**
   ```python
   if data_frame.empty:
       continue  # Skip empty chunks
   ```

### **Recovery Mechanisms**

- **Celery Retries:** Tasks automatically retry on transient failures
- **Blob Versioning:** Azure keeps blob versions for recovery
- **Idempotent Summarization:** DELETE + INSERT pattern
- **Manifest Tracking:** Database tracks processing state per file

---

## **Key Takeaways**

### **Design Principles**

1. **Streaming Over Loading:** Process files in chunks, never load entire files into memory
2. **Columnar Storage:** Parquet enables 10x compression and column-level queries
3. **Partitioning:** Both Parquet (by source/year/month) and PostgreSQL (by date) for performance
4. **Incremental Processing:** Only process new/changed data based on heuristics
5. **Normalization:** Handle Azure's variable schemas and unit of measure formats

### **Why This Architecture?**

- **Scalability:** Handle 10M+ line items per month
- **Performance:** Parquet + Trino = fast aggregations
- **Cost Efficiency:** Compressed storage, efficient queries
- **Reliability:** Chunked processing, error recovery, idempotent operations
- **Flexibility:** Handle Azure schema variations and optional manifests

### **Azure vs AWS Processing Differences**

| Aspect             | AWS                    | Azure                                |
| ------------------ | ---------------------- | ------------------------------------ |
| **File Format**    | Always gzip            | CSV or gzip                          |
| **Manifest**       | Always required        | Optional                             |
| **Date Column**    | identity/TimeInterval  | Date                                 |
| **Unit Handling**  | Simple                 | Requires normalization (multipliers) |
| **Service Name**   | ProductCode (simple)   | ServiceName/MeterCategory (fallback) |
| **Instance Type**  | Direct column          | JSON extraction                      |
| **Finalization**   | Invoice date available | Heuristic-based                      |
| **Authentication** | IAM Role               | Service Principal                    |
| **Storage**        | S3                     | Blob Storage                         |
| **Column Count**   | ~150 columns           | ~60 columns                          |

### **Trade-offs**

**Pros:**
- ✅ Handles millions of Azure line items
- ✅ Fast queries via Parquet + Trino
- ✅ Incremental updates
- ✅ Efficient storage (10x compression)
- ✅ Handles schema variations

**Cons:**
- ❌ Complex unit of measure normalization
- ❌ No invoice finalization signal (uses heuristics)
- ❌ Optional manifests require fallback logic
- ❌ Processing latency (30-90 minutes)
- ❌ Debugging across multiple systems

---

## **Related Documentation**

- [AWS CSV Processing](./aws-csv-processing.md) - Comparison with AWS CUR processing
- [Celery Tasks Architecture](./celery-tasks.md)
- [API Serializers and Provider Maps](./api-serializers-provider-maps.md)
- [Sources and Data Ingestion](./sources-and-data-ingestion.md)

---

## **Document Version**

- **Last Updated**: 2025-10-21
- **Koku Version**: Current
- **Author**: Architecture Documentation
