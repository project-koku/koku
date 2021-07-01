#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import logging
import math
import os
from datetime import datetime
from datetime import timedelta

from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.utils import timezone
from prometheus_client import push_to_gateway
from tenant_schemas.utils import schema_context

from api.dataexport.models import DataExportRequest
from api.dataexport.syncer import AwsS3Syncer
from api.dataexport.syncer import SyncedFileInColdStorageError
from api.iam.models import Tenant
from api.models import Provider
from api.provider.models import Sources
from api.utils import DateHelper
from koku import celery_app
from koku.metrics import REGISTRY
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.external.date_accessor import DateAccessor
from masu.processor import enable_trino_processing
from masu.processor.orchestrator import Orchestrator
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import DEFAULT
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import REMOVE_EXPIRED_DATA_QUEUE
from masu.prometheus_stats import QUEUES
from masu.util.aws.common import get_s3_resource
from masu.util.ocp.common import REPORT_TYPES

LOG = logging.getLogger(__name__)
_DB_FETCH_BATCH_SIZE = 2000


@celery_app.task(name="masu.celery.tasks.check_report_updates", queue=DEFAULT)
def check_report_updates(*args, **kwargs):
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator(*args, **kwargs)
    orchestrator.prepare()


@celery_app.task(name="masu.celery.tasks.remove_expired_data", queue=DEFAULT)
def remove_expired_data(simulate=False, line_items_only=False):
    """Scheduled task to initiate a job to remove expired report data."""
    today = DateAccessor().today()
    LOG.info("Removing expired data at %s", str(today))
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data(simulate, line_items_only)


def deleted_archived_with_prefix(s3_bucket_name, prefix):
    """
    Delete data from archive with given prefix.

    Args:
        s3_bucket_name (str): The s3 bucket name
        prefix (str): The prefix for deletion
    """
    s3_resource = get_s3_resource()
    s3_bucket = s3_resource.Bucket(s3_bucket_name)
    object_keys = [{"Key": s3_object.key} for s3_object in s3_bucket.objects.filter(Prefix=prefix)]
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


@celery_app.task(
    name="masu.celery.tasks.delete_archived_data",
    queue=REMOVE_EXPIRED_DATA_QUEUE,
    autoretry_for=(ClientError,),
    max_retries=10,
    retry_backoff=10,
)
def delete_archived_data(schema_name, provider_type, provider_uuid):
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

    if not (settings.ENABLE_S3_ARCHIVING or enable_trino_processing(provider_uuid, provider_type, schema_name)):
        LOG.info("Skipping delete_archived_data. Upload feature is disabled.")
        return
    else:
        message = f"Deleting S3 data for {provider_type} provider {provider_uuid} in account {schema_name}."
        LOG.info(message)

    # We need to normalize capitalization and "-local" dev providers.
    account = schema_name[4:]

    # Data in object storage does not use the local designation
    source_type = provider_type.replace("-local", "")
    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.CSV_DATA_TYPE}"
    prefix = f"{path_prefix}/{account}/{source_type}/source={provider_uuid}/"
    LOG.info("Attempting to delete our archived data in S3 under %s", prefix)
    deleted_archived_with_prefix(settings.S3_BUCKET_NAME, prefix)

    path_prefix = f"{Config.WAREHOUSE_PATH}/{Config.PARQUET_DATA_TYPE}"
    if provider_type == Provider.PROVIDER_OCP:
        prefixes = []
        for report_type in REPORT_TYPES:
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


@celery_app.task(name="masu.celery.tasks.clean_volume", queue=DEFAULT)
def clean_volume():
    """Clean up the volume in the worker pod."""
    LOG.info("Cleaning up the volume at %s " % Config.PVC_DIR)
    # get the billing months to use below
    months = DateAccessor().get_billing_months(Config.INITIAL_INGEST_NUM_MONTHS)
    db_accessor = ReportManifestDBAccessor()
    # this list is initialized with the .gitkeep file so that it does not get deleted
    assembly_ids_to_exclude = [".gitkeep"]
    # grab the assembly ids to exclude for each month
    for month in months:
        assembly_ids = db_accessor.get_last_seen_manifest_ids(month)
        assembly_ids_to_exclude.extend(assembly_ids)
    # now we want to loop through the files and clean up the ones that are not in the exclude list
    deleted_files = []
    retain_files = []

    datehelper = DateHelper()
    now = datehelper.now
    expiration_date = now - timedelta(seconds=Config.VOLUME_FILE_RETENTION)
    for [root, _, filenames] in os.walk(Config.PVC_DIR):
        for file in filenames:
            match = False
            for assembly_id in assembly_ids_to_exclude:
                if assembly_id in file:
                    match = True
            # if none of the assembly_ids that we care about were in the filename - we can safely delete it
            if not match:
                potential_delete = os.path.join(root, file)
                if os.path.exists(potential_delete):
                    file_datetime = datetime.fromtimestamp(os.path.getmtime(potential_delete))
                    file_datetime = timezone.make_aware(file_datetime)
                    if file_datetime < expiration_date:
                        os.remove(potential_delete)
                        deleted_files.append(potential_delete)
                    else:
                        retain_files.append(potential_delete)

    LOG.info("Removing all files older than %s", expiration_date)
    LOG.info("The following files were too new to delete: %s", retain_files)
    LOG.info("The following files were deleted: %s", deleted_files)


@celery_app.task(name="masu.celery.tasks.crawl_account_hierarchy", queue=DEFAULT)
def crawl_account_hierarchy(provider_uuid=None):
    """Crawl top level accounts to discover hierarchy."""
    if provider_uuid:
        _, polling_accounts = Orchestrator.get_accounts(provider_uuid=provider_uuid)
    else:
        _, polling_accounts = Orchestrator.get_accounts()
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


@celery_app.task(name="masu.celery.tasks.delete_provider_async", queue=PRIORITY_QUEUE)
def delete_provider_async(name, provider_uuid, schema_name):
    with schema_context(schema_name):
        LOG.info(f"Removing Provider without Source: {str(name)} ({str(provider_uuid)}")
        Provider.objects.get(uuid=provider_uuid).delete()


@celery_app.task(name="masu.celery.tasks.out_of_order_source_delete_async", queue=PRIORITY_QUEUE)
def out_of_order_source_delete_async(source_id):
    LOG.info(f"Removing out of order delete Source (ID): {str(source_id)}")
    Sources.objects.get(source_id=source_id).delete()


@celery_app.task(name="masu.celery.tasks.missing_source_delete_async", queue=PRIORITY_QUEUE)
def missing_source_delete_async(source_id):
    LOG.info(f"Removing missing Source: {str(source_id)}")
    Sources.objects.get(source_id=source_id).delete()


@celery_app.task(name="masu.celery.tasks.collect_queue_metrics", bind=True, queue=DEFAULT)
def collect_queue_metrics(self):
    """Collect queue metrics with scheduled celery task."""
    queue_len = {}
    with celery_app.pool.acquire(block=True) as conn:
        for queue, gauge in QUEUES.items():
            length = conn.default_channel.client.llen(queue)
            queue_len[queue] = length
            gauge.set(length)
    LOG.info("Celery queue backlog info: ")
    LOG.info(queue_len)
    LOG.debug("Pushing stats to gateway: %s", settings.PROMETHEUS_PUSHGATEWAY)
    try:
        push_to_gateway(
            settings.PROMETHEUS_PUSHGATEWAY, job="masu.celery.tasks.collect_queue_metrics", registry=REGISTRY
        )
    except OSError as exc:
        LOG.error("Problem reaching pushgateway: %s", exc)
        try:
            self.update_state(state="FAILURE", meta={"result": str(exc), "traceback": str(exc.__traceback__)})
        except TypeError as err:
            LOG.error("The following error occurred: %s " % err)
    return queue_len
