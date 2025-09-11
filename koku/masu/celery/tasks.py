#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import json
import logging

import requests
from botocore.exceptions import ClientError
from django.conf import settings
from django_tenants.utils import schema_context
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.exceptions import RetryError
from urllib3.util.retry import Retry

from api.common import log_json
from api.currency.currencies import VALID_CURRENCIES
from api.currency.models import ExchangeRates
from api.currency.utils import exchange_dictionary
from api.iam.models import Tenant
from api.models import Provider
from api.provider.models import Sources
from api.utils import DateHelper
from common.queues import DownloadQueue
from common.queues import PriorityQueue
from common.queues import SummaryQueue
from koku import celery_app
from koku.notifications import NotificationService
from masu.config import Config
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.processor import is_purge_trino_files_enabled
from masu.processor.orchestrator import Orchestrator
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import DEFAULT
from masu.prometheus_stats import QUEUES
from masu.util.aws.common import delete_s3_objects
from masu.util.aws.common import get_s3_resource
from masu.util.azure.azure_disk_size_scraper import AzureDiskSizeScraper
from masu.util.ocp.common import OCP_REPORT_TYPES
from reporting.models import TRINO_MANAGED_TABLES
from reporting_common.models import DelayedCeleryTasks
from reporting_common.models import DiskCapacity
from sources.tasks import delete_source

LOG = logging.getLogger(__name__)

PROVIDER_REPORT_TYPE_MAP = {
    Provider.PROVIDER_OCP: OCP_REPORT_TYPES,
}


@celery_app.task(name="masu.celery.tasks.check_report_updates", queue=DEFAULT)
def check_report_updates(*args, **kwargs):
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator(*args, **kwargs)
    LOG.info(log_json(msg="checking for report updates", args=args, kwargs=kwargs))
    orchestrator.prepare()


@celery_app.task(name="masu.celery.tasks.remove_expired_data", queue=DEFAULT)
def remove_expired_data(simulate=False):
    """Scheduled task to initiate a job to remove expired report data."""
    LOG.info("removing expired data")
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data(simulate)
    orchestrator.remove_expired_trino_partitions(simulate)


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
    deleted_archived_with_prefix(settings.S3_BUCKET_NAME, prefix)
    LOG.info("Deletion complete")


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
    context = {"service_task": "purge_old_data"}
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    s3_bucket = s3_resource.Bucket(s3_bucket_name)
    object_keys = [s3_object.key for s3_object in s3_bucket.objects.filter(Prefix=prefix)]
    LOG.info(f"starting objects: {len(object_keys)}")
    delete_s3_objects("purge masu endpoint", object_keys, context)


@celery_app.task(  # noqa: C901
    name="masu.celery.tasks.delete_archived_data",
    queue=SummaryQueue.DEFAULT,
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
    retries = Retry(
        total=5,
        allowed_methods={"GET"},
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retries))

    # Retrieve conversion rates from URL
    try:
        response = session.get(url)
        response.raise_for_status()
    except (HTTPError, RetryError) as e:
        LOG.error(f"Couldn't pull latest conversion rates from {url}")
        LOG.error(e)

        return rate_metrics

    data = response.json()

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


@celery_app.task(name="masu.celery.scrape_azure_storage_capacities", queue=DEFAULT)
def scrape_azure_storage_capacities():
    """Task to retrieve the Azure disk capacities.

    The Azure cost reports do not report disk capacities. Therefore, we retrieve
    the disk capacities and product substring from their documentation repos.
    """
    disk_fetcher = AzureDiskSizeScraper()
    disk_size_mapping = disk_fetcher.scrape_disk_size()
    if disk_size_mapping:
        for sku_prefix, disk_size in disk_size_mapping.items():
            DiskCapacity.objects.get_or_create(
                product_substring=sku_prefix,
                capacity=disk_size,
                provider_type=Provider.PROVIDER_AZURE,
            )
    return disk_size_mapping


@celery_app.task(name="masu.celery.tasks.crawl_account_hierarchy", queue=DEFAULT)
def crawl_account_hierarchy(provider_uuid=None):
    """Crawl top level accounts to discover hierarchy."""
    if provider_uuid:
        polling_accounts = Provider.objects.filter(uuid=provider_uuid)
    else:
        polling_accounts = Provider.polling_objects.all()
    LOG.info(f"Account hierarchy crawler found {len(polling_accounts)} accounts to scan")
    processed = 0
    skipped = 0
    for provider in polling_accounts:
        crawler = None

        # Look for a known crawler class to handle this provider
        if provider.type == Provider.PROVIDER_AWS:
            crawler = AWSOrgUnitCrawler(provider)

        if crawler:
            LOG.info(
                f"Starting account hierarchy crawler for type {provider.type} with provider_uuid: {provider.uuid}"
            )
            crawler.crawl_account_hierarchy()
            processed += 1
        else:
            LOG.info(f"No known crawler for account with provider_uuid: {provider.uuid} of type {provider.type}")
            skipped += 1
    LOG.info(f"Account hierarchy crawler finished. {processed} processed and {skipped} skipped")


@celery_app.task(name="masu.celery.tasks.check_cost_model_status", queue=DEFAULT)
def check_cost_model_status(provider_uuid=None):
    """Scheduled task to initiate source check and notification fire."""
    providers = []
    if provider_uuid:
        provider = Provider.objects.filter(uuid=provider_uuid).first()
        if provider and provider.type == Provider.PROVIDER_OCP:
            providers = [provider]
        else:
            LOG.info(f"Source {provider_uuid} is not an openshift source.")
            return
    else:
        providers = Provider.objects.filter(infrastructure_id__isnull=True, type=Provider.PROVIDER_OCP).all()
    LOG.info(f"Cost model status check found {len(providers)} providers to scan")
    processed = 0
    skipped = 0
    for provider in providers:
        with CostModelDBAccessor(provider.account.get("schema_name"), provider.uuid) as cmdba:
            if cmdba.cost_model:
                skipped += 1
                continue
        NotificationService().cost_model_notification(provider)
        processed += 1
    LOG.info(f"Cost model status check finished. {processed} notifications fired and {skipped} skipped")


@celery_app.task(name="masu.celery.tasks.check_for_stale_ocp_source", queue=DEFAULT)
def check_for_stale_ocp_source(provider_uuid=None):
    """Scheduled task to initiate source check and fire notifications."""
    with ReportManifestDBAccessor() as accessor:
        manifest_data = accessor.get_last_manifest_upload_datetime(provider_uuid)
    if manifest_data:
        LOG.info(f"Openshift stale cluster check found {len(manifest_data)} clusters to scan")
        processed = 0
        skipped = 0
        dh = DateHelper()
        check_date = dh.n_days_ago(dh.now, 3)
        for data in manifest_data:
            last_upload_time = data.get("most_recent_manifest")
            if not last_upload_time or last_upload_time < check_date:
                provider = Provider.objects.get(uuid=data.get("provider_id"))
                NotificationService().ocp_stale_source_notification(provider)
                processed += 1
            else:
                skipped += 1
        LOG.info(
            f"Openshift stale source status check finished. {processed} notifications fired and {skipped} skipped"
        )


@celery_app.task(name="masu.celery.tasks.delete_provider_async", queue=PriorityQueue.DEFAULT)
def delete_provider_async(name, provider_uuid, schema_name):
    with schema_context(schema_name):
        LOG.info(f"Removing Provider without Source: {str(name)} ({str(provider_uuid)}")
        try:
            Provider.objects.get(uuid=provider_uuid).delete()
        except Provider.DoesNotExist:
            LOG.warning(
                f"[delete_provider_async] Provider with uuid {provider_uuid} does not exist. Nothing to delete."
            )


@celery_app.task(name="masu.celery.tasks.out_of_order_source_delete_async", queue=PriorityQueue.DEFAULT)
def out_of_order_source_delete_async(source_id):
    LOG.info(f"Removing out of order delete Source (ID): {str(source_id)}")
    try:
        source = Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        LOG.warning(
            f"[out_of_order_source_delete_async] Source with ID {source_id} does not exist. Nothing to delete."
        )
        return
    # TODO re-enable this after stale demo sources are removed from stage
    # if source.account_id in settings.DEMO_ACCOUNTS:
    #     LOG.info(f"source `{source.source_id}` is a cost-demo source. skipping removal")
    #     return
    delete_source_helper(source)


@celery_app.task(name="masu.celery.tasks.missing_source_delete_async", queue=PriorityQueue.DEFAULT)
def missing_source_delete_async(source_id):
    LOG.info(f"Removing missing Source: {str(source_id)}")
    try:
        source = Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        LOG.warning(f"[missing_source_delete_async] Source with ID {source_id} does not exist. Nothing to delete.")
        return
    # TODO re-enable this after stale demo sources are removed from stage
    # if source.account_id in settings.DEMO_ACCOUNTS:
    #     LOG.info(f"source `{source.source_id}` is a cost-demo source. skipping removal")
    #     return
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


@celery_app.task(name="masu.celery.tasks.get_celery_queue_items", bind=True, queue=DEFAULT)
def get_celery_queue_items(self, queue_name=None, task_name=None):
    """
    Collect info on tasks in the celery queues.

    Parameters:
        queue_name (str): A specific queue to check task info for
        task_name (str): A specific task to get info for

    """
    queue_tasks = {}
    with celery_app.pool.acquire(block=True) as conn:
        if queue_name:
            queue_tasks[queue_name] = conn.default_channel.client.lrange(queue_name, 0, -1)
        else:
            for queue in QUEUES:
                queue_tasks[queue] = conn.default_channel.client.lrange(queue, 0, -1)

    decoded_tasks = {}
    for queue, tasks in queue_tasks.items():
        task_list = []
        for task in tasks:
            j = json.loads(task)
            t_header = j.get("headers", {})
            t_name = t_header.get("task", "")
            if task_name and t_name != task_name:
                continue
            t_info = {
                "name": t_name,
                "id": t_header.get("id", ""),
                "args": t_header.get("argsrepr", ""),
                "kwargs": t_header.get("kwargsrepr", ""),
            }
            task_list.append(t_info)
        decoded_tasks[queue] = task_list

    return decoded_tasks


@celery_app.task(name="masu.celery.tasks.trigger_delayed_tasks", queue=DownloadQueue.DEFAULT)
def trigger_delayed_tasks(*args, **kwargs):
    """Removes the expired records starting the delayed celery tasks."""
    DelayedCeleryTasks.trigger_delayed_tasks()
