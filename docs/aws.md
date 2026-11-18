# AWS Integration Guide

This guide covers how to integrate AWS Cost and Usage data with Koku for local development and testing.

**For production deployment**, AWS sources should be created through [Red Hat Hybrid Cloud Console](https://console.redhat.com) → Sources → Add Source → Amazon Web Services.

---

## Overview

Koku retrieves AWS cost data by:
1. AWS generates **Cost and Usage Reports (CUR)** and stores them in an S3 bucket
2. Koku uses an **IAM role** to access the S3 bucket (cross-account access)
3. Koku automatically downloads, processes, and summarizes the CUR data
4. Cost data appears in the console for analysis and reporting

---

## Prerequisites

### 1. AWS Cost and Usage Report (CUR) Setup

You need a Cost and Usage Report configured in your AWS account.

**Steps:**
1. Log into AWS Console → **Billing** → **Cost and Usage Reports**
2. Click **Create report**
3. Configure report settings:
   - **Report name**: `koku-cur` (or any name you prefer)
   - **Additional report details**: Check all boxes:
     - ✅ Include resource IDs
     - ✅ Split cost allocation data
   - **Data refresh settings**: ✅ Automatically refresh when charges are detected
   - **Time granularity**: **Hourly**
   - **Report versioning**: **Overwrite existing report**
   - **Compression type**: **GZIP**
   - **Report path prefix**: `cost-usage-reports/` (or any prefix)

4. **S3 bucket**: Select an existing bucket or create a new one
   - Bucket name example: `my-company-cur-bucket`
   - Region: us-east-1 (or your preferred region)

5. Click **Next** → **Review and Complete**

**Important:** CUR data can take **24 hours** to appear after initial setup.

### 2. S3 Bucket Policy

Your S3 bucket needs to allow Koku to access the CUR files.

**Add this bucket policy** (replace `YOUR_BUCKET_NAME`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowKokuReadAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_KOKU_AWS_ACCOUNT:role/KokuAccessRole"
      },
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET_NAME",
        "arn:aws:s3:::YOUR_BUCKET_NAME/*"
      ]
    }
  ]
}
```

### 3. IAM Role for Koku (Cross-Account Access)

Koku uses an IAM role to access your AWS account.

**Create IAM Role:**

1. AWS Console → **IAM** → **Roles** → **Create role**
2. **Trusted entity type**: AWS account
3. **An AWS account**:
   - For **production**: Enter Red Hat's AWS account ID (provided by Red Hat)
   - For **local dev**: Enter your own AWS account ID
4. Click **Next**
5. **Permissions**: Attach policy with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VisualEditor0",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "cur:DescribeReportDefinitions",
        "organizations:List*",
        "organizations:Describe*"
      ],
      "Resource": "*"
    }
  ]
}
```

6. **Role name**: `KokuAccessRole` (or any name)
7. Click **Create role**
8. **Copy the Role ARN** - you'll need this when creating the source

**Example ARN**: `arn:aws:iam::123456789012:role/KokuAccessRole`

---

## Local Development Setup

### Recommended: Admin Sources Endpoint (Development Mode)

**For local development**, use the simplified Admin Sources endpoint which bypasses the complex Sources integration.

**Prerequisites:**
- Local Koku environment running (`docker-compose up` or local dev setup)
- **`DEVELOPMENT=True`** in your environment (should be default for local dev)

**Steps:**

1. **Ensure Development Mode** is enabled:

   Check your `.env` file or environment variables:
   ```bash
   DEVELOPMENT=True
   ```

   This enables the `AdminSourcesSerializer` endpoint for easier local development.

2. **Set AWS credentials** (for local development only):

   Add to your `.env` file:
   ```bash
   AWS_ACCESS_KEY_ID=your_access_key_id
   AWS_SECRET_ACCESS_KEY=your_secret_access_key
   AWS_REGION=us-east-1
   ```

   **Note:** In production, credentials are managed securely through Red Hat's Sources service.

3. **Create Source via Admin Endpoint**:

   ```bash
   curl -X POST http://localhost:8000/api/cost-management/v1/sources/ \
     -H "Content-Type: application/json" \
     -d '{
       "name": "My AWS Source",
       "source_type": "AWS",
       "authentication": {
         "credentials": {
           "role_arn": "arn:aws:iam::123456789012:role/KokuAccessRole"
         }
       },
       "billing_source": {
         "data_source": {
           "bucket": "my-company-cur-bucket"
         }
       }
     }'
   ```

   **Note:** With `DEVELOPMENT=True`, all requests automatically use the `org1234567` schema, so no identity header is needed.

4. **Verify Source Created**:

   ```bash
   curl http://localhost:8000/api/cost-management/v1/sources/
   ```

   You should see your newly created source in the response.

**Data will be automatically downloaded** by the orchestrator on its scheduled run (typically runs every 2 hours).

---

### Production Sources Integration

**For production**, sources are created through Red Hat's Platform Sources service, which handles:
- Multi-step source creation workflow
- Kafka-based event streaming
- Authentication management
- Application linking

**Setting up full Sources integration locally is complex and not recommended for development.** The admin endpoint provides the same functionality with much less setup.

---

## Triggering Data Download

### Automatic (Recommended)

Koku's **Download Orchestrator** automatically checks for new data every **2 hours** (configurable via `DOWNLOAD_SCHEDULE` environment variable).

No manual intervention needed - just wait for the next scheduled run.

### Manual Trigger (For Testing)

If you need to trigger a download immediately for testing, use the **Masu download endpoint** (recommended):

**Masu Download Endpoint (Recommended)**

Trigger download for a specific provider:
```bash
# Download for specific provider
curl "http://localhost:5042/api/cost-management/v1/download/?provider_uuid=<PROVIDER_UUID>"

# Download for all providers of a type
curl "http://localhost:5042/api/cost-management/v1/download/?provider_type=AWS"

# Download for specific billing period
curl "http://localhost:5042/api/cost-management/v1/download/?provider_uuid=<PROVIDER_UUID>&bill_date=2025-01-01"

# Skip summarization (download only, no processing)
curl "http://localhost:5042/api/cost-management/v1/download/?provider_uuid=<PROVIDER_UUID>&summarize_reports=false"
```

**Response:**
```json
{
  "Download Request Task ID": "abc123-def456-ghi789"
}
```

You can use the task ID to monitor the Celery task progress in the worker logs.

---

## Verifying Data Ingestion

### 1. Check Provider Status

```bash
curl http://localhost:8000/api/cost-management/v1/providers/<provider_uuid>/
```

Look for:
- `"active": true` - Provider is active
- `"paused": false` - Provider is not paused
- `"data_updated_timestamp"` - Last time data was updated

### 2. Check Logs

**Koku Worker Logs:**
```bash
docker-compose logs -f koku-worker
```

Look for:
- `INFO Downloading report` - Download started
- `INFO Report processing complete` - Processing finished
- `ERROR` - Any errors during download/processing

**Koku Server Logs:**
```bash
docker-compose logs -f koku-server
```

### 3. Check Database

```bash
docker-compose exec koku-db psql -U postgres -d koku

-- Check for AWS bills
SELECT * FROM public.reporting_awscostentrybill LIMIT 10;

-- Check for AWS line items
SELECT COUNT(*) FROM org1234567.reporting_awscostentrylineitem_daily_summary;

-- Check manifests
SELECT * FROM public.reporting_common_costusagereportmanifest
WHERE provider_id = '<provider_uuid>'
ORDER BY creation_date DESC LIMIT 5;
```

### 4. Query Cost Data

```bash
curl "http://localhost:8000/api/cost-management/v1/reports/aws/costs/?filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[resolution]=daily"
```

If you get data back, ingestion is working!

---

## Troubleshooting

### "Provider authentication failed"

**Cause:** IAM role permissions or trust relationship issue.

**Solutions:**
1. Verify IAM role ARN is correct
2. Check IAM role trust relationship allows Koku's AWS account
3. Verify IAM role has `s3:GetObject` and `s3:ListBucket` permissions
4. Check S3 bucket policy allows the IAM role

### "Could not find manifest file"

**Cause:** CUR not configured correctly or data not yet generated.

**Solutions:**
1. Wait 24 hours after CUR creation
2. Verify CUR is configured with:
   - ✅ Include resource IDs
   - ✅ Hourly granularity
   - ✅ GZIP compression
   - ✅ Athena integration enabled
3. Check S3 bucket for files matching pattern: `s3://bucket/prefix/cur-name/cur-name/YYYYMMDD-YYYYMMDD/*.gz`

### "No data in reports"

**Cause:** Data not yet processed or download not triggered.

**Solutions:**
1. Check provider status (should be `active: true`)
2. Manually trigger download (see "Triggering Data Download")
3. Check worker logs for errors
4. Verify CUR data exists in S3 bucket
5. Ensure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set (local dev only)

### "Access Denied" errors in logs

**Cause:** S3 bucket permissions or IAM role issue.

**Solutions:**
1. Verify S3 bucket policy allows IAM role
2. Check IAM role has correct permissions
3. Ensure bucket and CUR are in the same AWS account
4. Try using AWS CLI to verify access:
   ```bash
   aws s3 ls s3://my-company-cur-bucket/cost-usage-reports/ --profile koku
   ```

---

## Data Processing Pipeline

For detailed information about how AWS data is processed, see:
- **[AWS CSV Processing Architecture](./architecture/csv-processing-aws.md)** - Deep dive into the AWS CUR processing pipeline
- **[Sources and Data Ingestion](./architecture/sources-and-data-ingestion.md)** - How Sources integration triggers data ingestion

**High-Level Flow:**
1. **Download Orchestrator** (Celery scheduled task) checks for new AWS CUR data every 2 hours
2. **Downloader** downloads CUR manifest and CSV files from S3
3. **Parquet Processor** converts CSV to Parquet format and uploads to MinIO/S3
4. **Summary Updater** aggregates data using Trino SQL and stores in PostgreSQL
5. **Cost data** is now available via REST API

---

## Testing with Sample Data

If you don't have access to real AWS data, you can use sample CUR files for testing.

**Sample CUR Generator:**
```bash
# Use the dev scripts to generate sample AWS data
docker-compose exec koku-server python /opt/koku/dev/scripts/create_test_customer.py --aws
```

**Or download sample CUR:**
- AWS provides sample CUR files: https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html

---

## Environment Variables

**Local Development:**
- `AWS_ACCESS_KEY_ID` - AWS access key (for S3 access)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (for S3 access)
- `AWS_REGION` - AWS region (default: `us-east-1`)
- `DOWNLOAD_SCHEDULE` - Cron schedule for automatic downloads (default: `0 */2 * * *` - every 2 hours)

**Production:**
- Credentials are managed by Red Hat's Sources service
- No need to set AWS credentials manually

---

## Related Documentation

- **AWS Setup (Official):** [docs/sources/aws.md](./sources/aws.md)
- **AWS CUR Setup Guide:** https://docs.aws.amazon.com/cur/latest/userguide/cur-create.html
- **IAM Roles:** https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html
- **Sources Integration:** [docs/architecture/sources-and-data-ingestion.md](./architecture/sources-and-data-ingestion.md)
- **CSV Processing:** [docs/architecture/csv-processing-aws.md](./architecture/csv-processing-aws.md)

---

## Production Deployment

For production deployment on Red Hat Hybrid Cloud Console:

1. Go to https://console.redhat.com
2. Navigate to **Settings** → **Sources** → **Add Source**
3. Select **Amazon Web Services**
4. Follow the wizard to:
   - Configure AWS CUR
   - Create IAM role
   - Add S3 bucket details
5. Enable **Cost Management** application
6. Data will automatically start flowing within 2-6 hours

**No manual API calls or configuration needed!**

---

## Document Metadata

- **Last Updated:** 2025-01-21
- **Koku Version:** Current
- **Author:** Architecture Documentation Team
