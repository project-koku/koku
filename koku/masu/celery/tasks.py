#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import logging
import math

import requests
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django_tenants.utils import schema_context

from api.currency.currencies import VALID_CURRENCIES
from api.currency.models import ExchangeRates
from api.currency.utils import exchange_dictionary
from api.dataexport.models import DataExportRequest
from api.dataexport.syncer import AwsS3Syncer
from api.dataexport.syncer import SyncedFileInColdStorageError
from api.iam.models import Tenant
from api.models import Provider
from api.provider.models import Sources
from api.utils import DateHelper
from koku import celery_app
from koku.notifications import NotificationService
from masu.config import Config
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor import is_purge_trino_files_enabled
from masu.processor.orchestrator import Orchestrator
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import DEFAULT
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import REMOVE_EXPIRED_DATA_QUEUE
from masu.prometheus_stats import QUEUES
from masu.util.aws.common import get_s3_resource
from masu.util.oci.common import OCI_REPORT_TYPES
from masu.util.ocp.common import OCP_REPORT_TYPES
from reporting.models import TRINO_MANAGED_TABLES
from sources.tasks import delete_source

LOG = logging.getLogger(__name__)
_DB_FETCH_BATCH_SIZE = 2000

PROVIDER_REPORT_TYPE_MAP = {
    Provider.PROVIDER_OCP: OCP_REPORT_TYPES,
    Provider.PROVIDER_OCI: OCI_REPORT_TYPES,
    Provider.PROVIDER_OCI_LOCAL: OCI_REPORT_TYPES,
}


@celery_app.task(name="masu.celery.tasks.check_report_updates", queue=DEFAULT)
def check_report_updates(*args, **kwargs):
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator(*args, **kwargs)
    orchestrator.prepare()


@celery_app.task(name="masu.celery.tasks.remove_expired_data", queue=DEFAULT)
def remove_expired_data(simulate=False):
    """Scheduled task to initiate a job to remove expired report data."""
    today = DateAccessor().today()
    LOG.info("Removing expired data at %s", str(today))
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data(simulate)


@celery_app.task(name="masu.celery.tasks.purge_trino_files", queue=DEFAULT)
def purge_s3_files(prefix, schema_name, provider_type, provider_uuid):
    """Remove files in a particular path prefix."""
    LOG.info(f"enable-purge-turnpikes schema: {schema_name}")
    if not is_purge_trino_files_enabled(schema_name):
        msg = f"Schema {schema_name} not enabled in unleash."
        LOG.info(msg)
        return msg
    if not schema_name or not provider_type or not provider_uuid:
        # Sanity-check all of these inputs in case somehow any receives an
        # empty value such as None or '' because we need to minimize the risk
        # of deleting unrelated files from our S3 bucket.
        messages = []
        if not schema_name:
            message = "missing required argument: schema_name"
            LOG.error(message)
            messages.append(message)
        if not provider_type:
            message = "missing required argument: provider_type"
            LOG.error(message)
            messages.append(message)
        if not provider_uuid:
            message = "missing required argument: provider_uuid"
            LOG.error(message)
            messages.append(message)
        raise TypeError("purge_trino_files() %s", ", ".join(messages))

    if settings.SKIP_MINIO_DATA_DELETION:
        LOG.info("Skipping purge_trino_files. MinIO in use.")
        return
    else:
        message = f"Deleting S3 data for {provider_type} provider {provider_uuid} in account {schema_name}."
        LOG.info(message)

    LOG.info("Attempting to delete our archived data in S3 under %s", prefix)
    remaining_objects = deleted_archived_with_prefix(settings.S3_BUCKET_NAME, prefix)
    LOG.info(f"Deletion complete. Remaining objects: {remaining_objects}")
    return remaining_objects


@celery_app.task(name="masu.celery.tasks.purge_manifest_records", queue=DEFAULT)
def purge_manifest_records(schema_name, provider_uuid, dates):
    """Remove files in a particular path prefix."""
    LOG.info(f"enable-purge-turnpikes schema: {schema_name}")
    if not is_purge_trino_files_enabled(schema_name):
        msg = f"Schema {schema_name} not enabled in unleash."
        LOG.info(msg)
        return msg
    with ReportManifestDBAccessor() as manifest_accessor:
        if dates.get("start_date") and dates.get("end_date"):
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_date_range(
                provider_uuid, dates.get("start_date"), dates.get("end_date")
            )
        elif dates.get("bill_date"):
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(
                provider_uuid=provider_uuid, bill_date=dates.get("bill_date")
            )
        else:
            msg = f"Dates requirements not met no manifest deleted, received: {dates}"
            LOG.info(msg)
            return msg
        manifest_id_list = [manifest.id for manifest in manifest_list]
        LOG.info(f"Attempting to delete the following manifests: {manifest_id_list}")
        manifest_accessor.bulk_delete_manifests(provider_uuid, manifest_id_list)
    provider = Provider.objects.filter(uuid=provider_uuid).first()
    provider.setup_complete = False
    provider.save()
    LOG.info(f"Provider ({provider_uuid}) setup_complete set to to False")


def deleted_archived_with_prefix(s3_bucket_name, prefix):
    """
    Delete data from archive with given prefix.

    Args:
        s3_bucket_name (str): The s3 bucket name
        prefix (str): The prefix for deletion
    """
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    s3_bucket = s3_resource.Bucket(s3_bucket_name)
    object_keys = [{"Key": s3_object.key} for s3_object in s3_bucket.objects.filter(Prefix=prefix)]
    LOG.info(f"Starting objects: {len(object_keys)}")
    batch_size = 1000  # AWS S3 delete API limits to 1000 objects per request.
    for batch_number in range(math.ceil(len(object_keys) / batch_size)):
        batch_start = batch_size * batch_number
        batch_end = batch_start + batch_size
        object_keys_batch = object_keys[batch_start:batch_end]
        s3_bucket.delete_objects(Delete={"Objects": object_keys_batch})

    remaining_objects = list(s3_bucket.objects.filter(Prefix=prefix))
    if remaining_objects:
        LOG.warning(
            "Found %s objects after attempting to delete all objects with prefix %s", len(remaining_objects), prefix
        )
    return remaining_objects


@celery_app.task(  # noqa: C901
    name="masu.celery.tasks.delete_archived_data",
    queue=REMOVE_EXPIRED_DATA_QUEUE,
    autoretry_for=(ClientError,),
    max_retries=10,
    retry_backoff=10,
)
def delete_archived_data(schema_name, provider_type, provider_uuid):  # noqa: C901
    """
    Delete archived data from our S3 bucket for a given provider.

    This function chiefly follows the deletion of a provider.

    This task is defined to attempt up to 10 retries using exponential backoff
    starting with a 10-second delay. This is intended to allow graceful handling
    of temporary AWS S3 connectivity issues because it is relatively important
    for us to delete this archived data.

    Args:
        schema_name (str): Koku user account (schema) name.
        provider_type (str): Koku backend provider type identifier.
        provider_uuid (UUID): Koku backend provider UUID.

    """
    if not schema_name or not provider_type or not provider_uuid:
        # Sanity-check all of these inputs in case somehow any receives an
        # empty value such as None or '' because we need to minimize the risk
        # of deleting unrelated files from our S3 bucket.
        messages = []
        if not schema_name:
            message = "missing required argument: schema_name"
            LOG.error(message)
            messages.append(message)
        if not provider_type:
            message = "missing required argument: provider_type"
            LOG.error(message)
            messages.append(message)
        if not provider_uuid:
            message = "missing required argument: provider_uuid"
            LOG.error(message)
            messages.append(message)
        raise TypeError("delete_archived_data() %s", ", ".join(messages))

    if settings.SKIP_MINIO_DATA_DELETION:
        LOG.info("Skipping delete_archived_data. MinIO in use.")
        return
    else:
        message = f"Deleting S3 data for {provider_type} provider {provider_uuid} in account {schema_name}."
        LOG.info(message)

    # We need to normalize capitalization and "-local" dev providers.

    # Existing schema will start with acct and we strip that prefix for use later
    # new customers include the org prefix in case an org-id and an account number might overlap
    account = schema_name.strip("acct")

    # Data in object storage does not use the local designation
    source_type = provider_type.replace("-local", "")
    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.CSV_DATA_TYPE}"
    prefix = f"{path_prefix}/{account}/{source_type}/source={provider_uuid}/"
    LOG.info("Attempting to delete our archived data in S3 under %s", prefix)
    deleted_archived_with_prefix(settings.S3_BUCKET_NAME, prefix)

    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.PARQUET_DATA_TYPE}"
    if provider_type in PROVIDER_REPORT_TYPE_MAP:
        prefixes = []
        for report_type in PROVIDER_REPORT_TYPE_MAP.get(provider_type):
            prefixes.append(f"{path_prefix}/{account}/{source_type}/{report_type}/source={provider_uuid}/")
            prefixes.append(f"{path_prefix}/daily/{account}/{source_type}/{report_type}/source={provider_uuid}/")
    else:
        prefixes = [
            f"{path_prefix}/{account}/{source_type}/source={provider_uuid}/",
            f"{path_prefix}/daily/{account}/{source_type}/raw/source={provider_uuid}/",
            f"{path_prefix}/daily/{account}/{source_type}/openshift/source={provider_uuid}/",
        ]
    for prefix in prefixes:
        LOG.info("Attempting to delete our archived data in S3 under %s", prefix)
        deleted_archived_with_prefix(settings.S3_BUCKET_NAME, prefix)

    if provider_type == Provider.PROVIDER_OCP:
        accessor = OCPReportDBAccessor(schema_name)
        for table, partition_column in TRINO_MANAGED_TABLES.items():
            accessor.delete_hive_partitions_by_source(table, partition_column, provider_uuid)


@celery_app.task(
    name="masu.celery.tasks.sync_data_to_customer",
    queue=DEFAULT,
    retry_kwargs={"max_retries": 5, "countdown": settings.COLD_STORAGE_RETRIVAL_WAIT_TIME},
)
def sync_data_to_customer(dump_request_uuid):
    """
    Scheduled task to sync normalized data to our customers S3 bucket.

    If the sync request raises SyncedFileInColdStorageError, this task
    will automatically retry in a set amount of time. This time is to give
    the storage solution time to retrieve a file from cold storage.
    This task will retry 5 times, and then fail.

    """
    dump_request = DataExportRequest.objects.get(uuid=dump_request_uuid)
    dump_request.status = DataExportRequest.PROCESSING
    dump_request.save()

    try:
        syncer = AwsS3Syncer(settings.S3_BUCKET_NAME)
        syncer.sync_bucket(
            dump_request.created_by.customer.schema_name,
            dump_request.bucket_name,
            (dump_request.start_date, dump_request.end_date),
        )
    except ClientError:
        LOG.exception(
            f"Encountered an error while processing DataExportRequest "
            f"{dump_request.uuid}, for {dump_request.created_by}."
        )
        dump_request.status = DataExportRequest.ERROR
        dump_request.save()
        return
    except SyncedFileInColdStorageError:
        LOG.info(
            f"One of the requested files is currently in cold storage for "
            f"DataExportRequest {dump_request.uuid}. This task will automatically retry."
        )
        dump_request.status = DataExportRequest.WAITING
        dump_request.save()
        try:
            raise sync_data_to_customer.retry(countdown=10, max_retries=5)
        except MaxRetriesExceededError:
            LOG.exception(
                f"Max retires exceeded for restoring a file in cold storage for "
                f"DataExportRequest {dump_request.uuid}, for {dump_request.created_by}."
            )
            dump_request.status = DataExportRequest.ERROR
            dump_request.save()
            return
    dump_request.status = DataExportRequest.COMPLETE
    dump_request.save()


# This task will process the autovacuum tuning as a background process
@celery_app.task(name="masu.celery.tasks.autovacuum_tune_schemas", queue=DEFAULT)
def autovacuum_tune_schemas():
    """Set the autovacuum table settings based on table size for all schemata."""
    tenants = Tenant.objects.values("schema_name")
    schema_names = [
        tenant.get("schema_name")
        for tenant in tenants
        if (tenant.get("schema_name") and tenant.get("schema_name") != "public")
    ]

    for schema_name in schema_names:
        LOG.info("Scheduling autovacuum tune task for %s", schema_name)
        # called in celery.py
        autovacuum_tune_schema.delay(schema_name)


@celery_app.task(name="masu.celery.tasks.get_daily_currency_rates", queue=DEFAULT)
def get_daily_currency_rates():
    """Task to get latest daily conversion rates."""
    rate_metrics = {}

    url = settings.CURRENCY_URL
    # Retrieve conversion rates from URL
    try:
        data = requests.get(url).json()
    except Exception as e:
        LOG.error(f"Couldn't pull latest conversion rates from {url}")
        LOG.error(e)
        return rate_metrics
    rates = data["rates"]
    # Update conversion rates in database
    for curr_type in rates.keys():
        if curr_type.upper() in VALID_CURRENCIES:
            value = rates[curr_type]
            try:
                exchange = ExchangeRates.objects.get(currency_type=curr_type.lower())
                LOG.info(f"Updating currency {curr_type} to {value}")
            except ExchangeRates.DoesNotExist:
                LOG.info(f"Creating the exchange rate {curr_type} to {value}")
                exchange = ExchangeRates(currency_type=curr_type.lower())
            rate_metrics[curr_type] = value
            exchange.exchange_rate = value
            exchange.save()
    exchange_dictionary(rate_metrics)
    return rate_metrics


@celery_app.task(name="masu.celery.tasks.crawl_account_hierarchy", queue=DEFAULT)
def crawl_account_hierarchy(provider_uuid=None):
    """Crawl top level accounts to discover hierarchy."""
    if provider_uuid:
        polling_accounts = Orchestrator.get_polling_accounts(provider_uuid=provider_uuid)
    else:
        polling_accounts = Orchestrator.get_polling_accounts()
    LOG.info("Account hierarchy crawler found %s accounts to scan" % len(polling_accounts))
    processed = 0
    skipped = 0
    for account in polling_accounts:
        crawler = None

        # Look for a known crawler class to handle this provider
        if account.get("provider_type") == Provider.PROVIDER_AWS:
            crawler = AWSOrgUnitCrawler(account)

        if crawler:
            LOG.info(
                "Starting account hierarchy crawler for type {} with provider_uuid: {}".format(
                    account.get("provider_type"), account.get("provider_uuid")
                )
            )
            crawler.crawl_account_hierarchy()
            processed += 1
        else:
            LOG.info(
                "No known crawler for account with provider_uuid: {} of type {}".format(
                    account.get("provider_uuid"), account.get("provider_type")
                )
            )
            skipped += 1
    LOG.info(f"Account hierarchy crawler finished. {processed} processed and {skipped} skipped")


@celery_app.task(name="masu.celery.tasks.check_cost_model_status", queue=DEFAULT)
def check_cost_model_status(provider_uuid=None):
    """Scheduled task to initiate source check and notification fire."""
    providers = []
    if provider_uuid:
        provider = Provider.objects.filter(uuid=provider_uuid).values("uuid", "type")
        if provider[0].get("type") == Provider.PROVIDER_OCP:
            providers = provider
        else:
            LOG.info(f"Source {provider_uuid} is not an openshift source.")
    else:
        providers = Provider.objects.filter(infrastructure_id__isnull=True, type=Provider.PROVIDER_OCP).all()
    LOG.info("Cost model status check found %s providers to scan" % len(providers))
    processed = 0
    skipped = 0
    for provider in providers:
        uuid = provider_uuid if provider_uuid else provider.uuid
        account = AccountsAccessor().get_account_from_uuid(uuid)
        cost_model_map = CostModelDBAccessor(account.get("schema_name"), uuid)
        if cost_model_map.cost_model:
            skipped += 1
        else:
            NotificationService().cost_model_notification(account)
            processed += 1
    LOG.info(f"Cost model status check finished. {processed} notifications fired and {skipped} skipped")


@celery_app.task(name="masu.celery.tasks.check_for_stale_ocp_source", queue=DEFAULT)
def check_for_stale_ocp_source(provider_uuid=None):
    """Scheduled task to initiate source check and fire notifications."""
    manifest_accessor = ReportManifestDBAccessor()
    if provider_uuid:
        manifest_data = manifest_accessor.get_last_manifest_upload_datetime(provider_uuid)
    else:
        manifest_data = manifest_accessor.get_last_manifest_upload_datetime()
    if manifest_data:
        LOG.info("Openshfit stale cluster check found %s clusters to scan" % len(manifest_data))
        processed = 0
        skipped = 0
        today = DateAccessor().today()
        check_date = DateHelper().n_days_ago(today, 3)
        for data in manifest_data:
            last_upload_time = data.get("most_recent_manifest")
            if not last_upload_time or last_upload_time < check_date:
                account = AccountsAccessor().get_account_from_uuid(data.get("provider_id"))
                NotificationService().ocp_stale_source_notification(account)
                processed += 1
            else:
                skipped += 1
        LOG.info(
            f"Openshift stale source status check finished. {processed} notifications fired and {skipped} skipped"
        )


@celery_app.task(name="masu.celery.tasks.delete_provider_async", queue=PRIORITY_QUEUE)
def delete_provider_async(name, provider_uuid, schema_name):
    with schema_context(schema_name):
        LOG.info(f"Removing Provider without Source: {str(name)} ({str(provider_uuid)}")
        try:
            Provider.objects.get(uuid=provider_uuid).delete()
        except Provider.DoesNotExist:
            LOG.warning(
                f"[delete_provider_async] Provider with uuid {provider_uuid} does not exist. Nothing to delete."
            )


@celery_app.task(name="masu.celery.tasks.out_of_order_source_delete_async", queue=PRIORITY_QUEUE)
def out_of_order_source_delete_async(source_id):
    LOG.info(f"Removing out of order delete Source (ID): {str(source_id)}")
    try:
        source = Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        LOG.warning(
            f"[out_of_order_source_delete_async] Source with ID {source_id} does not exist. Nothing to delete."
        )
        return
    if source.account_id in settings.DEMO_ACCOUNTS:
        LOG.info(f"source `{source.source_id}` is a cost-demo source. skipping removal")
        return
    delete_source_helper(source)


@celery_app.task(name="masu.celery.tasks.missing_source_delete_async", queue=PRIORITY_QUEUE)
def missing_source_delete_async(source_id):
    LOG.info(f"Removing missing Source: {str(source_id)}")
    try:
        source = Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        LOG.warning(f"[missing_source_delete_async] Source with ID {source_id} does not exist. Nothing to delete.")
        return
    if source.account_id in settings.DEMO_ACCOUNTS:
        LOG.info(f"source `{source.source_id}` is a cost-demo source. skipping removal")
        return
    delete_source_helper(source)


def delete_source_helper(source):
    if source.koku_uuid:
        # if there is a koku-uuid, a Provider also exists.
        # Go thru delete_source to remove the Provider and the Source
        delete_source(source.source_id, source.auth_header, source.koku_uuid, source.account_id, source.org_id)
    else:
        # here, no Provider exists, so just delete the Source
        source.delete()


@celery_app.task(name="masu.celery.tasks.collect_queue_metrics", bind=True, queue=DEFAULT)
def collect_queue_metrics(self):
    """Collect queue metrics with scheduled celery task."""
    queue_len = {}
    with celery_app.pool.acquire(block=True) as conn:
        for queue, gauge in QUEUES.items():
            length = conn.default_channel.client.llen(queue)
            queue_len[queue] = length
            gauge.set(length)
    LOG.debug(f"Celery queue backlog info: {queue_len}")
    return queue_len
