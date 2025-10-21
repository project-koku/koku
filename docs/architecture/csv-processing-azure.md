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

**Azure Blob Service:**
```python:181:212:koku/masu/external/downloader/azure/azure_service.py
def download_file(
    self,
    key: str,
    container_name: str,
    destination: str = None,
    suffix: str = AzureBlobExtension.csv.value,
    ingress_reports: list[str] = None,
) -> str:
    """Download file from Azure Blob Storage."""

    if not ingress_reports:
        cost_export = self.get_file_for_key(key, container_name)
        key = cost_export.name

    file_path = destination
    if not destination:
        temp_file = NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.close()
        file_path = temp_file.name

    try:
        blob_client = self._blob_service_client.get_blob_client(
            container=container_name,
            blob=key
        )
        with open(file_path, "wb") as blob_download:
            blob_download.write(blob_client.download_blob().readall())
    except AzureError as error:
        raise AzureServiceError(f"Failed to download file. Error: {error}")

    return file_path
```

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

**Processing Flow:**
```python:78:165:koku/masu/external/downloader/azure/azure_report_downloader.py
def create_daily_archives(...):
    """Create daily CSVs from incoming report."""

    # Determine processing start date
    process_date = get_processing_date(
        s3_csv_path, manifest_id, provider_uuid, start_date, end_date, context, tracing_id
    )

    # Detect date column (Azure uses "Date" in modern exports)
    time_interval = pd.read_csv(local_file, nrows=0).columns.intersection(
        {"UsageDateTime", "Date", "date", "usagedatetime"}
    )[0]

    # Legacy check
    if time_interval not in ["Date", "date"]:
        msg = (
            "Unsupported Azure report schema (legacy version) detected. "
            "The report contains the 'UsageDateTime' column, which indicates an outdated format. "
            "Please use a modern report schema (which uses the 'Date' column)."
        )
        LOG.warning(log_json(msg=msg, context=context))
        return [], {}

    # Read CSV in chunks
    with pd.read_csv(
        local_file,
        chunksize=settings.PARQUET_PROCESSING_BATCH_SIZE,  # 200,000 rows
        parse_dates=[time_interval],
        dtype=pd.StringDtype(storage="pyarrow"),
    ) as reader:
        for i, data_frame in enumerate(reader):
            if data_frame.empty:
                continue

            # Sort by date and filter to process_date forward
            data_frame = data_frame.set_index(time_interval, drop=False).sort_index()
            data_frame = data_frame.loc[process_date:end_date]

            if data_frame.empty:
                continue

            # Extract unique dates
            dates = data_frame[time_interval].unique()
            batch_date_range.add(data_frame.index[0].strftime(DATE_FORMAT))
            batch_date_range.add(data_frame.index[-1].strftime(DATE_FORMAT))

            # Write daily files
            for date in dates:
                daily_data = data_frame.loc[[date]]
                if daily_data.empty:
                    continue

                day_path = pd.to_datetime(date).strftime(DATE_FORMAT)
                day_file = f"{day_path}_manifestid-{manifest_id}_basefile-{base_name}_batch-{i}.csv"
                day_filepath = f"{directory}/{day_file}"

                daily_data.to_csv(day_filepath, index=False, header=True)

                # Upload to S3 immediately
                copy_local_report_file_to_s3_bucket(
                    tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, context
                )
                daily_file_names.append(day_filepath)
```

**Output Structure:**
```
org1234567/azure/csv/
├── 2025-01-01_manifestid-123_basefile-export_batch-0.csv
├── 2025-01-01_manifestid-123_basefile-export_batch-1.csv
├── 2025-01-02_manifestid-123_basefile-export_batch-0.csv
└── ...
```

#### **2.2 Processing Date Logic**

Azure doesn't have an invoice finalization date, so Koku uses heuristics:

```python:43:75:koku/masu/external/downloader/azure/azure_report_downloader.py
def get_processing_date(...):
    """Determine what date to start processing from."""
    dh = DateHelper()

    # Process everything if:
    # 1. Previous year
    # 2. Previous month (and not first day of month)
    # 3. Initial setup (setup_complete=False)
    # 4. Ingress reports (manually uploaded)
    if (
        start_date.year < dh.today.year and dh.today.day > 1
        or start_date.month < dh.today.month and dh.today.day > 1
        or not check_provider_setup_complete(provider_uuid)
        or ingress_reports
    ):
        process_date = start_date
        process_date = ReportManifestDBAccessor().set_manifest_daily_start_date(
            manifest_id, process_date
        )
    else:
        # Current month: check for existing data in S3
        process_date = get_or_clear_daily_s3_by_date(
            s3_csv_path, provider_uuid, start_date, end_date, manifest_id, context, tracing_id
        )

    return process_date
```

#### **2.3 Column Requirements**

**Required Columns:**
```python:18:50:koku/masu/util/azure/common.py
INGRESS_REQUIRED_COLUMNS = {
    "additionalinfo",
    "billingaccountid",
    "billingaccountname",
    "billingperiodenddate",
    "billingperiodstartdate",
    "consumedservice",
    "costinbillingcurrency",
    "date",
    "effectiveprice",
    "metercategory",
    "meterid",
    "metername",
    "meterregion",
    "metersubcategory",
    "offerid",
    "productname",
    "publishername",
    "publishertype",
    "quantity",
    "reservationid",
    "reservationname",
    "resourceid",
    "resourcelocation",
    "resourcename",
    "servicefamily",
    "serviceinfo1",
    "serviceinfo2",
    "subscriptionid",
    "tags",
    "unitofmeasure",
    "unitprice",
}

# Alternate column names (Azure schema variations)
INGRESS_REQUIRED_ALT_COLUMNS = [
    ["billingcurrencycode", "billingcurrency"],
    ["resourcegroup", "resourcegroupname"]
]
```

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

**Azure-Specific Processor:**
```python:18:47:koku/masu/processor/azure/azure_report_parquet_processor.py
class AzureReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        # Define Azure-specific column types
        numeric_columns = [
            "quantity",
            "resourcerate",
            "costinbillingcurrency",
            "effectiveprice",
            "unitprice",
            "paygprice",
        ]

        date_columns = [
            "date",
            "billingperiodstartdate",
            "billingperiodenddate"
        ]

        boolean_columns = ["resource_id_matched"]

        column_types = {
            "numeric_columns": numeric_columns,
            "date_columns": date_columns,
            "boolean_columns": boolean_columns,
        }

        # Determine table name
        if "openshift" in s3_path:
            table_name = TRINO_OCP_ON_AZURE_DAILY_TABLE
        else:
            table_name = TRINO_LINE_ITEM_TABLE

        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            column_types=column_types,
            table_name=table_name,
        )
```

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

**Process:**
```python:40:104:koku/masu/processor/azure/azure_report_parquet_summary_updater.py
def update_summary_tables(self, start_date, end_date, **kwargs):
    """Populate the summary tables for reporting."""

    # 1. Get cost model markup
    with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
        markup = cost_model_accessor.markup
        markup_value = float(markup.get("value", 0)) / 100  # 10% = 0.10

    # 2. Handle partitions for UI summary tables
    with schema_context(self._schema):
        self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

    # 3. Get billing records
    with AzureReportDBAccessor(self._schema) as accessor:
        with schema_context(self._schema):
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            bill_ids = [str(bill.id) for bill in bills]
            current_bill_id = bills.first().id if bills else None

        if current_bill_id is None:
            LOG.info(log_json(msg="no bill was found, skipping summarization"))
            return start_date, end_date

        # 4. Process in 5-day chunks (TRINO_DATE_STEP)
        for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
            LOG.info(log_json(
                msg="updating Azure report summary tables via Trino",
                start_date=start,
                end_date=end,
            ))

            # 4a. DELETE existing summary data for date range
            filters = {"cost_entry_bill_id": current_bill_id}
            accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                self._provider.uuid, start, end, filters
            )

            # 4b. INSERT new summary data via Trino
            accessor.populate_line_item_daily_summary_table_trino(
                start, end, self._provider.uuid, current_bill_id, markup_value
            )

            # 4c. Populate UI summary tables
            accessor.populate_ui_summary_tables(start, end, self._provider.uuid)

        # 5. Populate tag summaries
        accessor.populate_tags_summary_table(bill_ids, start_date, end_date)

        # 6. Apply tag mappings
        accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)

        # 7. Update bill timestamps
        for bill in bills:
            if bill.summary_data_creation_datetime is None:
                bill.summary_data_creation_datetime = timezone.now()
            bill.summary_data_updated_datetime = timezone.now()
            bill.save()

    return start_date, end_date
```

#### **4.2 Trino SQL Query**
**File:** `trino_sql/azure/reporting_azurecostentrylineitem_daily_summary.sql`

**Query Structure:**
```sql:21:98:koku/masu/database/trino_sql/azure/reporting_azurecostentrylineitem_daily_summary.sql
-- Step 1: CTE to aggregate raw Parquet data
WITH cte_line_items AS (
    SELECT
        date(date) as usage_date,
        INTEGER '{{bill_id}}' as cost_entry_bill_id,

        -- Subscription handling (use GUID if ID is empty)
        coalesce(nullif(subscriptionid, ''), subscriptionguid) as subscription_guid,
        coalesce(nullif(subscriptionname, ''), nullif(subscriptionid, ''), subscriptionguid) as subscription_name,

        -- Location and service
        resourcelocation as resource_location,
        coalesce(nullif(servicename, ''), metercategory) as service_name,

        -- Instance type from AdditionalInfo JSON
        json_extract_scalar(json_parse(additionalinfo), '$.ServiceType') as instance_type,

        -- Costs and usage
        cast(quantity as DECIMAL(24,9)) as usage_quantity,
        cast(costinbillingcurrency as DECIMAL(24,9)) as pretax_cost,
        coalesce(nullif(billingcurrencycode, ''), billingcurrency) as currency,

        -- Tags as JSON
        json_parse(tags) as tags,

        -- Resource tracking
        resourceid as instance_id,
        cast(source as UUID) as source_uuid,

        -- Unit of measure normalization
        CASE
            WHEN regexp_like(split_part(unitofmeasure, ' ', 1), '^\d+(\.\d+)?$')
                AND NOT (unitofmeasure = '100 Hours' AND metercategory='Virtual Machines')
                AND NOT split_part(unitofmeasure, ' ', 2) = ''
            THEN cast(split_part(unitofmeasure, ' ', 1) as INTEGER)
            ELSE 1
        END as multiplier,

        CASE
            WHEN split_part(unitofmeasure, ' ', 2) IN ('Hours', 'Hour')
                THEN 'Hrs'
            WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                THEN 'GB-Mo'
            WHEN split_part(unitofmeasure, ' ', 2) != ''
                AND split_part(unitofmeasure, ' ', 3) = ''
            THEN split_part(unitofmeasure, ' ', 2)
            ELSE unitofmeasure
        END as unit_of_measure

    FROM hive.{{schema}}.azure_line_items
    WHERE source = '{{source_uuid}}'
        AND year = '{{year}}'
        AND month = '{{month}}'
        AND date >= TIMESTAMP '{{start_date}}'
        AND date < date_add('day', 1, TIMESTAMP '{{end_date}}')
),
-- Get enabled tag keys from PostgreSQL
cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
    from postgres.{{schema}}.reporting_enabledtagkeys
    where enabled = true
    and provider_type = 'Azure'
)
-- Step 2: Aggregate and insert into PostgreSQL
SELECT
    uuid() as uuid,
    li.usage_date AS usage_start,
    li.usage_date AS usage_end,
    li.cost_entry_bill_id,
    li.subscription_guid,
    li.resource_location,
    li.service_name,
    li.instance_type,

    -- Azure meters usage in large blocks (e.g., "100 Hours")
    -- Normalize to standard units and multiply usage
    sum(li.pretax_cost) AS pretax_cost,
    sum(li.usage_quantity * li.multiplier) AS usage_quantity,
    max(li.unit_of_measure) as unit_of_measure,
    max(li.currency) as currency,

    -- Filter tags to only enabled keys
    cast(
        map_filter(
            cast(li.tags as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
    ) as tags,

    -- Resource tracking
    array_agg(DISTINCT li.instance_id) as instance_ids,
    count(DISTINCT li.instance_id) as instance_count,

    li.source_uuid,

    -- Apply markup
    sum(cast(li.pretax_cost * {{markup}} AS decimal(24,9))) as markup_cost,
    li.subscription_name

FROM cte_line_items AS li
CROSS JOIN cte_pg_enabled_keys as pek

GROUP BY
    li.usage_date,
    li.cost_entry_bill_id,
    13, -- matches column num for tags map_filter
    li.subscription_guid,
    li.resource_location,
    li.instance_type,
    li.service_name,
    li.source_uuid,
    li.subscription_name
```

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

**Structure:**
```python:112:156:koku/reporting/provider/azure/models.py
class AzureCostEntryLineItemDailySummary(models.Model):
    """Azure line item daily summary."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    uuid = models.UUIDField(primary_key=True)
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)

    # Subscription (account equivalent)
    subscription_guid = models.TextField(null=False)
    subscription_name = models.TextField(null=True)

    # Resource details
    instance_type = models.TextField(null=True)
    service_name = models.TextField(null=True)
    resource_location = models.TextField(null=True)

    # Date range
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)

    # Usage metrics
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.TextField(null=True)

    # Cost metrics
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)

    # Resource tracking
    instance_ids = ArrayField(models.TextField(), null=True)
    instance_count = models.IntegerField(null=True)

    # Metadata
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
```

#### **5.2 Table Partitioning**
**Monthly partitions for efficient querying:**

```sql
-- Automatic partition creation
CREATE TABLE reporting_azurecostentrylineitem_daily_summary_2025_01
    PARTITION OF reporting_azurecostentrylineitem_daily_summary
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE reporting_azurecostentrylineitem_daily_summary_2025_02
    PARTITION OF reporting_azurecostentrylineitem_daily_summary
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
```

**Benefits:**
- Query only relevant month(s)
- Efficient partition pruning
- Easy data retention (drop old partitions)
- Parallel index creation

#### **5.3 Indexes**
```python:127:136:koku/reporting/provider/azure/models.py
indexes = [
    models.Index(fields=["usage_start"], name="ix_azurecstentrydlysumm_start"),
    models.Index(fields=["resource_location"], name="ix_azurecstentrydlysumm_svc"),
    models.Index(fields=["subscription_guid"], name="ix_azurecstentrydlysumm_sub_id"),
    models.Index(fields=["instance_type"], name="ix_azurecstentrydlysumm_instyp"),
    models.Index(fields=["subscription_name"], name="ix_azurecstentrydlysumm_sub_na"),
]
# GIN functional index on service_name:
# (upper(service_name) gin_trgm_ops) - for case-insensitive partial matching
```

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
