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
```python
GCP_COLUMN_LIST = [
    # Billing account
    "billing_account_id",

    # Service details
    "service.id",
    "service.description",
    "sku.id",
    "sku.description",

    # Time range
    "usage_start_time",
    "usage_end_time",
    "export_time",

    # Project details
    "project.id",
    "project.name",
    "project.labels",           # JSON
    "project.ancestry_numbers",

    # Labels and metadata
    "labels",                   # JSON - customer labels
    "system_labels",            # JSON - GCP system labels

    # Location
    "location.location",
    "location.country",
    "location.region",
    "location.zone",

    # Cost columns
    "cost",                     # Main cost field
    "currency",
    "currency_conversion_rate",
    "credits",                  # JSON - array of credits

    # Usage
    "usage.amount",
    "usage.unit",
    "usage.amount_in_pricing_units",
    "usage.pricing_unit",

    # Invoice
    "invoice.month",            # e.g., "202501" (YYYYMM format)
    "cost_type",                # regular, tax, adjustment, rounding error

    # Resource
    "resource.name",
    "resource.global_name",
]
```

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
**File:** `gcp_report_downloader.py:scan_start`, `scan_end`

Unlike AWS/Azure (which process fixed monthly reports), GCP checks for **new/updated data daily**:

```python:184:200:koku/masu/external/downloader/gcp/gcp_report_downloader.py
@cached_property
def scan_start(self):
    """The start partition date we check for data in BigQuery."""
    dh = DateHelper()
    provider = Provider.objects.filter(uuid=self._provider_uuid).first()

    if provider.setup_complete:
        # Established provider: check last 10 days
        scan_start = dh.today - relativedelta(days=10)
    else:
        # New provider: initial ingest (default: 2 months)
        months_delta = Config.INITIAL_INGEST_NUM_MONTHS - 1
        scan_start = dh.today - relativedelta(months=months_delta)
        scan_start = scan_start.replace(day=1)

    return scan_start.date()

@cached_property
def scan_end(self):
    """The end partition date we check for data in BigQuery."""
    return DateHelper().today.date()
```

**Why Different from AWS/Azure?**
- BigQuery receives **continuous updates** (not monthly batch files)
- Data can be corrected/adjusted retroactively
- Need to check for **changes** in already-processed dates
- Credits and adjustments can appear days/weeks after original usage

#### **1.2 Partition-to-Export Mapping**
**File:** `gcp_report_downloader.py:bigquery_export_to_partition_mapping()`

**The Problem:** How do we know if data for a specific date has changed since we last processed it?

**The Solution:** Track the `export_time` for each partition date:

```python:238:270:koku/masu/external/downloader/gcp/gcp_report_downloader.py
def bigquery_export_to_partition_mapping(self):
    """
    Grab the partition_date & max(export_time) from BigQuery.

    Returns:
        dict: {partition_date: export_time}
        example: {"2022-05-19": "2022-05-19 19:40:16.385000 UTC"}
    """
    mapping = {}
    try:
        client = bigquery.Client()
        export_partition_date_query = f"""
            SELECT
                DATE(_PARTITIONTIME) AS partition_date,
                DATETIME(max(export_time))
            FROM `{self.table_name}`
            WHERE DATE(_PARTITIONTIME) BETWEEN '{self.scan_start}'
                AND '{self.scan_end}'
            GROUP BY partition_date
            ORDER BY partition_date
        """
        eq_result = client.query(export_partition_date_query).result()

        for row in eq_result:
            mapping[row[0]] = row[1].replace(tzinfo=settings.UTC)

    except GoogleCloudError as err:
        msg = "could not query table for partition date information"
        raise GCPReportDownloaderError(msg) from err

    return mapping
```

**Example Output:**
```python
{
    datetime.date(2025, 1, 18): datetime(2025, 1, 19, 2, 30, 0, tzinfo=UTC),
    datetime.date(2025, 1, 19): datetime(2025, 1, 20, 2, 15, 0, tzinfo=UTC),
    datetime.date(2025, 1, 20): datetime(2025, 1, 21, 2, 45, 0, tzinfo=UTC),
}
```

#### **1.3 Manifest Collection (Pseudo-Manifests)**
**File:** `gcp_report_downloader.py:collect_new_manifests()`

Since GCP doesn't have traditional manifest files, Koku creates **pseudo-manifests**:

```python:272:300:koku/masu/external/downloader/gcp/gcp_report_downloader.py
def collect_new_manifests(self, current_manifests, bigquery_mappings):
    """
    Generate a dict representing an analog to other providers' "manifest" files.
    """
    new_manifests = []

    for bigquery_pd, bigquery_et in bigquery_mappings.items():
        manifest_export_time = current_manifests.get(bigquery_pd)

        # Check if data changed since last processing
        if (manifest_export_time and manifest_export_time != bigquery_et) or not manifest_export_time:
            # New or updated data found!
            bill_date = bigquery_pd.replace(day=1)
            invoice_month = bill_date.strftime("%Y%m")  # "202501"
            file_name = f"{invoice_month}_{bigquery_pd}"

            manifest_metadata = {
                "assembly_id": f"{bigquery_pd}|{bigquery_et}",
                "bill_date": bill_date,
                "files": [file_name],
            }
            new_manifests.append(manifest_metadata)

    if not new_manifests:
        LOG.info("no new manifests created")

    return new_manifests
```

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
**File:** `gcp_report_downloader.py:download_file()`

**"Downloading" from BigQuery = Executing SQL Query:**

```python:433:504:koku/masu/external/downloader/gcp/gcp_report_downloader.py
def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
    """
    Download a file from GCP storage bucket.

    For BigQuery exports: this executes a SQL query and writes results to CSV.
    """
    paths_list = []
    directory_path = self._get_local_directory_path()
    os.makedirs(directory_path, exist_ok=True)

    if not self.ingress_reports:
        try:
            # Extract partition_date from filename
            filename = os.path.splitext(key)[0]
            partition_date = filename.split("_")[-1]  # "202501_2025-01-15" → "2025-01-15"

            # Build SELECT query
            query = f"""
                SELECT {self.build_query_select_statement()}
                FROM `{self.table_name}`
                WHERE DATE(_PARTITIONTIME) = '{partition_date}'
            """

            client = bigquery.Client()
            query_job = client.query(query).result()

        except GoogleCloudError as err:
            msg = "Could not query table for billing information."
            raise GCPReportDownloaderError(msg) from err

        try:
            column_list = GCP_COLUMN_LIST.copy()
            column_list.append("partition_date")

            # Write results to CSV in batches
            for i, rows in enumerate(batch(query_job, settings.PARQUET_PROCESSING_BATCH_SIZE)):
                full_local_path = self._get_local_file_path(directory_path, partition_date, i)
                msg = f"downloading subset of {partition_date} to {full_local_path}"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

                with open(full_local_path, "w") as f:
                    writer = csv.writer(f)
                    writer.writerow(column_list)
                    writer.writerows(rows)

                paths_list.append(full_local_path)

        except OSError as exc:
            msg = "Could not create GCP billing data csv file."
            raise GCPReportDownloaderError(msg) from exc

    # Create daily archives
    file_names, date_range = create_daily_archives(
        self.tracing_id,
        self.account,
        self._provider_uuid,
        paths_list,
        manifest_id,
        start_date,
        self.context,
        self.ingress_reports,
    )

    return key, None, DateHelper().today, file_names, date_range
```

**Query SELECT Statement Building:**
```python:423:431:koku/masu/external/downloader/gcp/gcp_report_downloader.py
def build_query_select_statement(self):
    """Helper to build query select statement."""
    columns_list = GCP_COLUMN_LIST.copy()

    # Convert JSON columns to strings
    columns_list = [
        f"TO_JSON_STRING({col})" if col in ("labels", "system_labels", "project.labels", "credits")
        else col
        for col in columns_list
    ]

    # Add partition date
    columns_list.append("DATE(_PARTITIONTIME) as partition_date")

    return ",".join(columns_list)
```

**Batching:**
- BigQuery can return millions of rows
- Process in chunks: `PARQUET_PROCESSING_BATCH_SIZE` (200,000 rows)
- Write multiple CSV files per partition date
- Files named: `{invoice_month}_{partition_date}_{batch_num}.csv`

---

### **Phase 2: Daily Archive Creation**

#### **2.1 CSV Splitting by Invoice Month & Partition Date**
**File:** `gcp_report_downloader.py:create_daily_archives()`

**GCP's Unique Challenge: Crossover Data**

**What is Crossover Data?**
- Usage from one month can appear in a different `invoice.month`
- Example: January 31 usage might be in February's invoice due to processing delays
- Or: Credit applied in March for January usage (appears in March invoice)

**Processing Flow:**
```python:62:139:koku/masu/external/downloader/gcp/gcp_report_downloader.py
def create_daily_archives(...):
    """
    Create daily CSVs from incoming report and archive to S3.

    GCP-specific: Must handle invoice.month crossover.
    """
    daily_file_names = []
    date_range = {}

    try:
        for local_file_path in local_file_paths:
            file_name = os.path.basename(local_file_path).split("/")[-1]
            dh = DateHelper()
            directory = os.path.dirname(local_file_path)

            data_frame = pd_read_csv(local_file_path)
            data_frame = add_label_columns(data_frame)  # Ensure labels columns exist

            # Get unique usage days
            unique_usage_days = pd.to_datetime(data_frame["usage_start_time"]).dt.date.unique()
            days = list({day.strftime("%Y-%m-%d") for day in unique_usage_days})
            date_range = {"start": min(days), "end": max(days)}

            # Group by invoice month (critical for crossover data)
            for invoice_month in data_frame["invoice.month"].unique():
                # Handle bad ingress reports with null invoice months
                if pd.isna(invoice_month):
                    continue

                invoice_filter = data_frame["invoice.month"] == invoice_month
                invoice_month_data = data_frame[invoice_filter]

                # Further split by partition date
                partition_dates = invoice_month_data.partition_date.unique()
                for partition_date in partition_dates:
                    partition_date_filter = invoice_month_data["partition_date"] == partition_date
                    invoice_partition_data = invoice_month_data[partition_date_filter]

                    # Determine S3 path based on invoice month (not usage date!)
                    start_of_invoice = dh.invoice_month_start(invoice_month)
                    s3_csv_path = get_path_prefix(
                        account,
                        Provider.PROVIDER_GCP,
                        provider_uuid,
                        start_of_invoice,  # Based on invoice month!
                        Config.CSV_DATA_TYPE
                    )

                    day_file = f"{invoice_month}_{partition_date}_{file_name}"

                    if ingress_reports:
                        # Ingress flow: clear existing S3 files
                        date_time = datetime.datetime.strptime(partition_date, "%Y-%m-%d")
                        clear_s3_files(
                            s3_csv_path, provider_uuid, date_time,
                            "manifestid", manifest_id, context, tracing_id, invoice_month
                        )
                        partition_filename = ReportManifestDBAccessor().update_and_get_day_file(
                            partition_date, manifest_id
                        )
                        day_file = f"{invoice_month}_{partition_filename}"

                    day_filepath = f"{directory}/{day_file}"

                    # Write CSV
                    invoice_partition_data.to_csv(day_filepath, index=False, header=True)

                    # Upload to S3
                    copy_local_report_file_to_s3_bucket(
                        tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, context
                    )

                    daily_file_names.append(day_filepath)

    except Exception as e:
        msg = f"unable to create daily archives from: {local_file_paths}. reason: {e}"
        LOG.info(log_json(tracing_id, msg=msg, context=context))
        raise CreateDailyArchivesError(msg)

    return daily_file_names, date_range
```

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
**File:** `masu/util/gcp/common.py:add_label_columns()`

GCP labels are optional - ensure columns always exist:

```python:98:112:koku/masu/util/gcp/common.py
def add_label_columns(data_frame):
    """Add empty label columns if they don't exist."""
    label_data = False
    system_label_data = False

    columns = list(data_frame)
    for column in columns:
        if "labels" == column:
            label_data = True
        if "system_labels" == column:
            system_label_data = True

    if not label_data:
        data_frame["labels"] = ""
    if not system_label_data:
        data_frame["system_labels"] = ""

    return data_frame
```

---

### **Phase 3: Parquet Conversion**

#### **3.1 CSV to Parquet Transformation**
**File:** `gcp_report_parquet_processor.py`

**GCP-Specific Processor:**
```python:19:50:koku/masu/processor/gcp/gcp_report_parquet_processor.py
class GCPReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        # Define GCP-specific column types
        numeric_columns = [
            "cost",
            "currency_conversion_rate",
            "usage_amount",
            "usage_amount_in_pricing_units",
            "credit_amount",
            "daily_credits",
        ]

        date_columns = [
            "usage_start_time",
            "usage_end_time",
            "export_time",
            "partition_time"
        ]

        boolean_columns = ["ocp_matched"]

        # Determine table name based on path
        if "openshift" in s3_path:
            table_name = TRINO_OCP_ON_GCP_DAILY_TABLE
        elif "daily" in s3_path:
            table_name = TRINO_LINE_ITEM_DAILY_TABLE
        else:
            table_name = TRINO_LINE_ITEM_TABLE

        column_types = {
            "numeric_columns": numeric_columns,
            "date_columns": date_columns,
            "boolean_columns": boolean_columns,
        }

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

#### **3.2 Trino Table Structure**

```sql
CREATE TABLE IF NOT EXISTS hive.org1234567.gcp_line_items (
    -- Billing account
    billing_account_id varchar,

    -- Service details
    service_id varchar,
    service_description varchar,
    sku_id varchar,
    sku_description varchar,

    -- Time
    usage_start_time timestamp,
    usage_end_time timestamp,
    export_time timestamp,

    -- Project
    project_id varchar,
    project_name varchar,
    project_labels varchar,
    project_ancestry_numbers varchar,

    -- Labels (JSON strings)
    labels varchar,
    system_labels varchar,

    -- Location
    location_location varchar,
    location_country varchar,
    location_region varchar,
    location_zone varchar,

    -- Cost
    cost double,
    currency varchar,
    currency_conversion_rate double,

    -- Usage
    usage_amount double,
    usage_unit varchar,
    usage_amount_in_pricing_units double,
    usage_pricing_unit varchar,

    -- Credits (JSON string - array)
    credits varchar,

    -- Invoice
    invoice_month varchar,  -- "202501"
    cost_type varchar,      -- "regular", "tax", "adjustment", "rounding_error"

    -- Resource
    resource_name varchar,
    resource_global_name varchar,

    -- Partition columns
    partition_date varchar,
    source varchar,
    year varchar,
    month varchar
) WITH (
    external_location = 's3a://koku-bucket/org1234567/gcp/parquet/',
    format = 'PARQUET',
    partitioned_by = ARRAY['source', 'year', 'month']
)
```

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
**File:** `trino_sql/gcp/get_invoice_month_dates.sql`

**The Challenge:** GCP invoices can contain data spanning multiple months due to crossover.

**The Solution:** Dynamically determine date range from data:

```sql:1:30:koku/masu/database/trino_sql/gcp/get_invoice_month_dates.sql
SELECT
    min(usage_start_time),
    max(usage_start_time)
FROM hive.{{schema}}.gcp_line_items_daily
WHERE
    -- Extend start/end dates at month boundaries to catch crossover data
    -- This catches both 2025-07-31 and 2025-09-01 with invoice 202508
    usage_start_time >=
    CASE
        WHEN DAY(DATE({{start_date}})) = 1
            THEN DATE({{start_date}}) - INTERVAL '3' DAY
        ELSE DATE({{start_date}})
    END
    AND usage_start_time <=
    CASE
        WHEN LAST_DAY_OF_MONTH(DATE({{end_date}})) = DATE({{end_date}})
            THEN DATE({{end_date}}) + INTERVAL '3' DAY
        ELSE DATE({{end_date}})
    END
    AND invoice_month = {{invoice_month}}
    AND source = {{source_uuid}}
    AND (
        -- Check multiple year/month partitions for crossover data
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}})) AS VARCHAR)
         AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}})) AS VARCHAR)
         AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}})) AS VARCHAR), 2, '0'))
        OR
        -- Previous and next months for crossover
        ...
    )
```

**Example:**
```python
# Processing invoice "202501" (January 2025)
# Query finds:
#   min(usage_start_time) = 2024-12-30  # Credit from previous month
#   max(usage_start_time) = 2025-02-02  # Usage from next month

# Koku will then summarize ALL this data under invoice 202501
```

#### **4.2 Daily Summary Table Population**
**File:** `gcp_report_parquet_summary_updater.py:update_summary_tables()`

```python:43:118:koku/masu/processor/gcp/gcp_report_parquet_summary_updater.py
def update_summary_tables(self, start_date, end_date, **kwargs):
    """Populate the summary tables for reporting."""

    start_date, end_date = self._get_sql_inputs(start_date, end_date)

    # 1. Get cost model markup
    with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
        markup = cost_model_accessor.markup
        markup_value = float(markup.get("value", 0)) / 100

    # 2. Handle partitions for UI summary tables
    with schema_context(self._schema):
        self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

    # 3. Get billing records
    with GCPReportDBAccessor(self._schema) as accessor:
        with schema_context(self._schema):
            invoice_month = start_date.strftime("%Y%m")

            # Dynamically lookup invoice period date range from Trino data
            invoice_dates = accessor.fetch_invoice_month_dates(
                start_date, end_date, invoice_month, self._provider.uuid
            )
            invoice_start, invoice_end = invoice_dates[0]

            bills = accessor.bills_for_provider_uuid(
                self._provider.uuid, invoice_month=invoice_month
            )
            bill_ids = [str(bill.id) for bill in bills]
            current_bill_id = bills.first().id if bills else None

            if current_bill_id is None:
                LOG.info(log_json(msg="no bill was found, skipping summarization"))
                return start_date, end_date

            # 4. Process in 5-day chunks
            for start, end in date_range_pair(invoice_start, invoice_end, step=settings.TRINO_DATE_STEP):
                LOG.info(log_json(
                    msg="updating GCP report summary tables from parquet",
                    start_date=start,
                    end_date=end,
                    invoice_month=invoice_month,
                    bill_id=current_bill_id,
                ))

                # 4a. DELETE existing summary data
                filters = {"cost_entry_bill_id": current_bill_id}
                accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                    self._provider.uuid, start, end, filters
                )

                # 4b. INSERT new summary data via Trino
                accessor.populate_line_item_daily_summary_table_trino(
                    start, end, self._provider.uuid, current_bill_id,
                    markup_value, invoice_month
                )

                # 4c. Populate UI summary tables
                accessor.populate_ui_summary_tables(
                    start, end, self._provider.uuid, invoice_month
                )

                # 4d. Populate GCP topology (project hierarchy)
                accessor.populate_gcp_topology_information_tables(
                    self._provider, start_date, end_date, invoice_month
                )

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

#### **4.3 Trino SQL Query**
**File:** `trino_sql/gcp/reporting_gcpcostentrylineitem_daily_summary.sql`

```sql:26:85:koku/masu/database/trino_sql/gcp/reporting_gcpcostentrylineitem_daily_summary.sql
-- Get enabled tag keys from PostgreSQL
WITH cte_pg_enabled_keys AS (
    SELECT array_agg(key ORDER BY key) as keys
    FROM postgres.{{schema}}.reporting_enabledtagkeys
    WHERE enabled = true
      AND provider_type = 'GCP'
)
SELECT
    uuid() as uuid,
    INTEGER '{{bill_id}}' as cost_entry_bill_id,

    -- Billing and project details
    billing_account_id as account_id,
    project_id,
    max(project_name) as project_name,

    -- Service and SKU
    service_id,
    max(service_description) as service_alias,
    sku_id,
    max(sku_description) as sku_alias,

    -- Date (daily aggregation)
    date(usage_start_time) as usage_start,
    date(usage_start_time) as usage_end,

    -- Location
    nullif(location_region, '') as region,

    -- Instance type from system_labels JSON
    json_extract_scalar(json_parse(system_labels), '$["compute.googleapis.com/machine_spec"]') as instance_type,

    -- Usage
    max(usage_pricing_unit) as unit,
    cast(sum(usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,

    -- Tags (filter to enabled keys only)
    cast(
        map_filter(
            cast(json_parse(labels) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
    ) as tags,

    -- Cost
    max(currency) as currency,
    cost_type as line_item_type,
    cast(sum(cost) AS decimal(24,9)) as unblended_cost,
    cast(sum(cost * {{markup}}) AS decimal(24,9)) as markup_cost,

    -- Metadata
    UUID '{{source_uuid}}' as source_uuid,
    invoice_month,

    -- Credits: Extract amount from JSON array and sum
    sum(
        ((cast(COALESCE(json_extract_scalar(json_parse(credits), '$["amount"]'), '0') AS decimal(24,9))) * 1000000)
        / 1000000
    ) as credit_amount

FROM hive.{{schema}}.{{table}}
CROSS JOIN cte_pg_enabled_keys as pek

WHERE source = '{{source_uuid}}'
    -- Multi-partition scan to catch crossover data
    AND (
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}})) AS VARCHAR)
         AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}})) AS VARCHAR)
         AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR)
         AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR), 2, '0'))
    )
    AND invoice_month = '{{invoice_month}}'
    AND usage_start_time >= TIMESTAMP '{{start_date}}'
    AND usage_start_time < date_add('day', 1, TIMESTAMP '{{end_date}}')

GROUP BY
    billing_account_id,
    project_id,
    service_id,
    sku_id,
    date(usage_start_time),
    date(usage_end_time),
    location_region,
    json_extract_scalar(json_parse(system_labels), '$["compute.googleapis.com/machine_spec"]'),
    16, -- matches column num for tags map_filter
    cost_type,
    invoice_month
```

**GCP-Specific Handling:**

1. **Instance Type Extraction:**
   ```sql
   json_extract_scalar(
       json_parse(system_labels),
       '$["compute.googleapis.com/machine_spec"]'
   ) as instance_type
   ```

2. **Credits Processing:**
   ```sql
   -- Credits is JSON array: [{"amount": -5.23, "name": "Committed use discount"}]
   sum(
       cast(
           COALESCE(json_extract_scalar(json_parse(credits), '$["amount"]'), '0')
           AS decimal(24,9)
       ) * 1000000 / 1000000  -- Precision handling
   ) as credit_amount
   ```

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
**Table:** `reporting_gcpcostentrylineitem_daily_summary`

```python:57:111:koku/reporting/provider/gcp/models.py
class GCPCostEntryLineItemDailySummary(models.Model):
    """A daily aggregation of line items."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    uuid = models.UUIDField(primary_key=True)
    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)

    # Billing and project
    account_id = models.CharField(max_length=20)  # billing_account_id
    project_id = models.CharField(max_length=256)
    project_name = models.CharField(max_length=256)

    # Service and SKU
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    sku_id = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)

    # Date range
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)

    # Location and instance
    region = models.CharField(max_length=50, null=True)
    instance_type = models.CharField(max_length=50, null=True)

    # Usage metrics
    unit = models.CharField(max_length=63, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    # Cost metrics
    line_item_type = models.CharField(max_length=256, null=True)  # cost_type
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)

    # Credits
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)

    # Invoice
    invoice_month = models.CharField(max_length=256, null=True, blank=True)  # "202501"

    # Metadata
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
```

#### **5.2 Indexes**
```python:75:83:koku/reporting/provider/gcp/models.py
indexes = [
    models.Index(fields=["usage_start"], name="gcp_summary_usage_start_idx"),
    models.Index(fields=["instance_type"], name="gcp_summary_instance_type_idx"),
    GinIndex(fields=["tags"], name="gcp_tags_idx"),
    models.Index(fields=["project_id"], name="gcp_summary_project_id_idx"),
    models.Index(fields=["project_name"], name="gcp_summary_project_name_idx"),
    models.Index(fields=["service_id"], name="gcp_summary_service_id_idx"),
    models.Index(fields=["service_alias"], name="gcp_summary_service_alias_idx"),
]
```

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
```python
# 1. Group by invoice_month during CSV splitting
for invoice_month in data_frame["invoice.month"].unique():
    invoice_filter = data_frame["invoice.month"] == invoice_month
    invoice_month_data = data_frame[invoice_filter]
    # ... process each invoice month separately

# 2. Store in S3 paths by invoice month
start_of_invoice = dh.invoice_month_start(invoice_month)
s3_csv_path = get_path_prefix(account, Provider.PROVIDER_GCP, provider_uuid, start_of_invoice, ...)

# 3. Query extends date range at month boundaries
SELECT min(usage_start), max(usage_start)
WHERE invoice_month = '202501'
-- Returns: 2024-12-29 to 2025-02-03 (crossover included!)

# 4. Trino scans multiple partitions
WHERE (year='2024' AND month='12')
   OR (year='2025' AND month='01')
   OR (year='2025' AND month='02')
AND invoice_month = '202501'  # Filter to specific invoice
```

### **Challenge 2: No Traditional Manifest Files**

**Problem:** BigQuery doesn't provide manifest files listing available data

**Solution: Pseudo-Manifests based on export_time**
```python
# Track when each partition was last exported
bigquery_mappings = {
    date(2025, 1, 18): datetime(2025, 1, 19, 2, 30),  # export_time
    date(2025, 1, 19): datetime(2025, 1, 20, 2, 15),
}

# Compare with stored export_times
current_manifests = {
    date(2025, 1, 18): datetime(2025, 1, 19, 2, 30),  # Matches
    date(2025, 1, 19): datetime(2025, 1, 19, 2, 10),  # Different! Data changed
}

# Create manifest for changed partition
if bigquery_et != manifest_export_time:
    new_manifest = {
        "assembly_id": f"{partition_date}|{bigquery_et}",
        "bill_date": partition_date.replace(day=1),
        "files": [f"{invoice_month}_{partition_date}"]
    }
```

### **Challenge 3: BigQuery Query Performance**

**Problem:** Scanning entire table is expensive and slow

**Solution: Partition Pruning**
```sql
-- BAD: Full table scan (expensive!)
SELECT * FROM `project.dataset.billing_export`
WHERE usage_start_time >= '2025-01-15'

-- GOOD: Partition pruning (10-100x faster!)
SELECT * FROM `project.dataset.billing_export`
WHERE DATE(_PARTITIONTIME) = '2025-01-15'
  AND usage_start_time >= '2025-01-15'
```

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
```sql
-- Extract and sum credits from JSON
sum(
    cast(
        COALESCE(
            json_extract_scalar(json_parse(credits), '$["amount"]'),
            '0'
        ) AS decimal(24,9)
    ) * 1000000 / 1000000  -- Precision handling for decimal
) as credit_amount
```

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
```sql
json_extract_scalar(
    json_parse(system_labels),
    '$["compute.googleapis.com/machine_spec"]'
) as instance_type
```

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
```sql
WHERE (
    (year = '2024' AND month = '12')  # Previous month crossover
    OR
    (year = '2025' AND month = '01')  # Current invoice month
    OR
    (year = '2025' AND month = '02')  # Next month crossover
)
AND invoice_month = '202501'  # Still filter to specific invoice!
```

---

## **Error Handling & Recovery**

### **Common Issues**

1. **BigQuery Authentication Errors**
   ```python
   except GoogleCloudError as err:
       msg = "Could not query table for billing information."
       raise GCPReportDownloaderError(msg) from err
   ```

2. **Table Not Found**
   ```python
   # Validate table exists during provider setup
   GCPProvider().cost_usage_source_is_reachable(credentials, data_source)
   ```

3. **Null Invoice Months**
   ```python
   # Skip bad ingress reports with null invoice months
   if pd.isna(invoice_month):
       continue
   ```

4. **Empty Query Results**
   ```python
   if not bigquery_mappings:
       LOG.info("no new data found in BigQuery")
       return []
   ```

5. **CSV Write Errors**
   ```python
   except OSError as exc:
       msg = "Could not create GCP billing data csv file."
       raise GCPReportDownloaderError(msg) from exc
   ```

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
