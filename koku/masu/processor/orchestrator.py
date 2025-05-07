#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report Processing Orchestrator."""
import copy
import logging
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

from celery import chord
from celery import group
from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.conf import settings

from api.common import log_json
from api.provider.models import check_provider_setup_complete
from api.provider.models import Provider
from api.utils import DateHelper
from common.queues import DownloadQueue
from common.queues import get_customer_queue
from common.queues import SummaryQueue
from hcs.tasks import collect_hcs_report_data_from_manifest
from hcs.tasks import HCS_QUEUE
from masu.config import Config
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.processor import is_cloud_source_processing_disabled
from masu.processor import is_customer_large
from masu.processor import is_source_disabled
from masu.processor.tasks import get_report_files
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import remove_expired_trino_partitions
from masu.processor.tasks import summarize_reports
from masu.processor.worker_cache import WorkerCache
from masu.util.aws.common import update_account_aliases
from subs.tasks import extract_subs_data_from_reports
from subs.tasks import SUBS_EXTRACTION_QUEUE

LOG = logging.getLogger(__name__)


def get_billing_month_start(in_date):
    """Return the start of the month for the input."""
    if isinstance(in_date, str):
        return parser.parse(in_date).replace(day=1).date()
    elif isinstance(in_date, datetime):
        return in_date.replace(day=1).date()
    else:
        return in_date.replace(day=1)


def get_billing_months(number_of_months):
    """Return a list of datetimes for the number of months to ingest

    Args:
        number_of_months (int) The the number of months (bills) to ingest.

    Returns:
        (list) of datetime.datetime objects in YYYY-MM-DD format.
        example: ["2020-01-01", "2020-02-01"]
    """
    months = []
    current_month = DateHelper().this_month_start
    for month in range(number_of_months):
        calculated_month = current_month + relativedelta(months=-month)
        months.append(calculated_month.date())
    return months


def check_currently_processing(schema, provider):
    result = False
    if provider.polling_timestamp:
        # Set processing delta wait time
        process_wait_delta = datetime.now(tz=settings.UTC) - timedelta(days=settings.PROCESSING_WAIT_TIMER)
        if is_customer_large(schema):
            process_wait_delta = datetime.now(tz=settings.UTC) - timedelta(days=settings.LARGE_PROCESSING_WAIT_TIMER)
        # Check processing, if polling timestamp more recent than updated timestamp skip polling
        if provider.data_updated_timestamp:
            if provider.polling_timestamp > provider.data_updated_timestamp:
                result = True
                # Check failed processing, if updated timestamp not updated in x days we should polling again
                if process_wait_delta > provider.data_updated_timestamp:
                    result = False
        # Fallback to creation timestamp if its a new provider
        else:
            # Dont trigger provider that has no updated timestamp
            result = True
            # Enable initial ingest for new providers
            if datetime.now(tz=settings.UTC) - timedelta(days=1) < provider.created_timestamp:
                result = False
            # Reprocess new providers that may have fialed to complete their first download
            if process_wait_delta > provider.created_timestamp:
                result = False

    return result


class Orchestrator:
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(
        self,
        provider_uuid=None,
        provider_type=None,
        bill_date=None,
        queue_name=None,
        **kwargs,
    ):
        self.dh = DateHelper()
        self.worker_cache = WorkerCache()
        self.bill_date = bill_date
        self.provider_uuid = provider_uuid
        self.provider_type = provider_type
        self.queue_name = queue_name
        self.ingress_reports = kwargs.get("ingress_reports")
        self.ingress_report_uuid = kwargs.get("ingress_report_uuid")
        self._summarize_reports = kwargs.get("summarize_reports", True)

    def get_polling_batch(self):
        if self.provider_uuid:
            providers = Provider.objects.filter(uuid=self.provider_uuid)
        else:
            filters = {}
            if self.provider_type:
                filters["type"] = self.provider_type
            providers = Provider.polling_objects.get_polling_batch(filters=filters)

        batch = []
        for provider in providers:
            schema_name = provider.account.get("schema_name")
            # Check processing delta wait and skip polling if provider not completed processing
            if check_currently_processing(schema_name, provider):
                # We still need to update the timestamp between runs
                LOG.info(
                    log_json(
                        "get_polling_batch",
                        msg="processing currently in progress for provider",
                        schema=schema_name,
                        provider=provider.uuid,
                    )
                )
                provider.polling_timestamp = self.dh.now_utc
                provider.save(update_fields=["polling_timestamp"])
                continue
            # This needs to happen after the first check since we use the original polling_timestamp
            provider.polling_timestamp = self.dh.now_utc
            provider.save(update_fields=["polling_timestamp"])
            # If a source is disabled/re-enabled it may not be collected till after the process_wait_delta expires
            if is_cloud_source_processing_disabled(schema_name):
                LOG.info(log_json("get_polling_batch", msg="processing disabled for schema", schema=schema_name))
                continue
            if is_source_disabled(provider.uuid):
                LOG.info(
                    log_json(
                        "get_polling_batch",
                        msg="processing disabled for source",
                        schema=schema_name,
                        provider_uuid=provider.uuid,
                    )
                )
                continue
            batch.append(provider)
        return batch

    def get_reports(self, provider_uuid):
        """
        Get months for provider to process.

        Args:
            (String) provider uuid to determine if initial setup is complete.

        Returns:
            (List) List of datetime objects.

        """
        if self.bill_date:
            if self.ingress_reports:
                bill_date = f"{self.bill_date}01"
                return [get_billing_month_start(bill_date)]
            return [get_billing_month_start(self.bill_date)]

        if Config.INGEST_OVERRIDE or not check_provider_setup_complete(provider_uuid):
            number_of_months = Config.INITIAL_INGEST_NUM_MONTHS
        else:
            number_of_months = 2

        return get_billing_months(number_of_months)

    def start_manifest_processing(  # noqa: C901
        self,
        customer_name,
        credentials,
        data_source,
        provider_type,
        schema_name,
        provider_uuid,
        report_month,
        **kwargs,
    ):
        """
        Start processing an account's manifest for the specified report_month.

        Args:
            (String) customer_name - customer name
            (String) credentials - credentials object
            (String) data_source - report storage location
            (String) schema_name - db tenant
            (String) provider_uuid - provider unique identifier
            (Date)   report_month - month to get latest manifest

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([{"key": full_file_path "local_file": "local file name"}]): List of report files.
            (Boolean) - Whether we are processing this manifest
        """
        # Switching initial ingest to use priority queue for QE tests based on QE_SCHEMA flag
        if self.queue_name is not None and self.provider_uuid is not None:
            SUMMARY_QUEUE = self.queue_name
            REPORT_QUEUE = self.queue_name
            HCS_Q = self.queue_name
        else:
            SUMMARY_QUEUE = get_customer_queue(schema_name, SummaryQueue)
            REPORT_QUEUE = get_customer_queue(schema_name, DownloadQueue)
            HCS_Q = HCS_QUEUE
        reports_tasks_queued = False
        downloader = ReportDownloader(
            customer_name=customer_name,
            credentials=credentials,
            data_source=data_source,
            provider_type=provider_type,
            provider_uuid=provider_uuid,
            report_name=None,
            ingress_reports=self.ingress_reports,
        )
        # only GCP returns more than one manifest.
        manifest_list = downloader.download_manifest(report_month)
        report_tasks = []
        LOG.info(log_json("start_manifest_processing", msg="creating manifest list", schema=schema_name))
        for manifest in manifest_list:
            tracing_id = manifest.get("assembly_id", manifest.get("request_id", "no-request-id"))
            report_files = manifest.get("files", [])
            filenames = [file.get("local_file") for file in report_files]
            LOG.info(
                log_json(tracing_id, msg=f"manifest {tracing_id} contains the files: {filenames}", schema=schema_name)
            )

            if manifest:
                LOG.debug("Saving all manifest file names.")
                # This creates all the initial report status entries
                record_all_manifest_files(
                    manifest["manifest_id"],
                    [report.get("local_file") for report in manifest.get("files", [])],
                    tracing_id,
                )

            LOG.info(log_json(tracing_id, msg="found manifests", context=manifest, schema=schema_name))

            last_report_index = len(report_files) - 1
            # Override the queue if we determine a provider is large based on report count
            if len(report_files) > settings.XL_REPORT_COUNT:
                LOG.info(
                    log_json(
                        tracing_id,
                        msg="marking provider large as report files exceed threshold.",
                        file_count=len(report_files),
                        Threshold=settings.XL_REPORT_COUNT,
                        schema=schema_name,
                    )
                )
                SUMMARY_QUEUE = get_customer_queue(schema_name, SummaryQueue, xl_provider=True)
                REPORT_QUEUE = get_customer_queue(schema_name, DownloadQueue, xl_provider=True)
            for i, report_file_dict in enumerate(report_files):
                local_file = report_file_dict.get("local_file")
                report_file = report_file_dict.get("key")

                # Check if report file is complete or in progress.
                if record_report_status(manifest["manifest_id"], local_file, "no_request"):
                    LOG.info(
                        log_json(tracing_id, msg="file was already processed", filename=local_file, schema=schema_name)
                    )
                    continue

                cache_key = f"{provider_uuid}:{report_file}"
                if self.worker_cache.task_is_running(cache_key):
                    LOG.info(
                        log_json(
                            tracing_id, msg="file processing is in progress", filename=local_file, schema=schema_name
                        )
                    )
                    continue

                report_context = manifest.copy()
                report_context["current_file"] = report_file
                report_context["local_file"] = local_file
                report_context["key"] = report_file
                report_context["request_id"] = tracing_id

                if (
                    provider_type
                    in [
                        Provider.PROVIDER_OCP,
                        Provider.PROVIDER_GCP,
                    ]
                    or i == last_report_index
                ):
                    # This create_table flag is used by the ParquetReportProcessor
                    # to create a Hive/Trino table.
                    # To reduce the number of times we check Trino/Hive tables, we just do this
                    # on the final file of the set.
                    report_context["create_table"] = True

                # this is used to create bills for previous months on GCP
                if provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
                    if assembly_id := manifest.get("assembly_id"):
                        report_month = assembly_id.split("|")[0]
                elif provider_type == Provider.PROVIDER_OCP:
                    # The report month is used in the metadata of OCP files in s3.
                    # Setting the report_month to the start date allows us to
                    # delete the correct data for daily operator files
                    report_month = manifest.get("start")
                # add the tracing id to the report context
                # This defaults to the celery queue
                LOG.info(log_json(tracing_id, msg="queueing download", schema=schema_name))
                report_tasks.append(
                    get_report_files.s(
                        customer_name,
                        credentials,
                        data_source,
                        provider_type,
                        schema_name,
                        provider_uuid,
                        report_month,
                        report_context,
                        tracing_id=tracing_id,
                        ingress_reports=self.ingress_reports,
                        ingress_reports_uuid=self.ingress_report_uuid,
                    ).set(queue=REPORT_QUEUE)
                )
                LOG.info(log_json(tracing_id, msg="download queued", schema=schema_name))

        manifest_list = [manifest.get("manifest_id") for manifest in manifest_list]
        LOG.info(
            log_json(
                "start_manifest_processing",
                msg="created manifest list",
                report_tasks=report_tasks,
                summarize_reports=self._summarize_reports,
                schema=schema_name,
            )
        )
        if report_tasks:
            if self._summarize_reports:
                reports_tasks_queued = True
                hcs_task = collect_hcs_report_data_from_manifest.s().set(queue=HCS_Q)
                summary_task = summarize_reports.s(
                    manifest_list=manifest_list, ingress_report_uuid=self.ingress_report_uuid
                ).set(queue=SUMMARY_QUEUE)
                LOG.info(
                    log_json(
                        "start_manifest_processing",
                        msg="created summary_task signature",
                        schema=schema_name,
                        summary_task=str(summary_task),
                        hcs_task=str(hcs_task),
                    )
                )
                # data source contains fields from applications.extra and metered is the key that gates subs processing.
                subs_task = extract_subs_data_from_reports.s(data_source.get("metered", "")).set(
                    queue=SUBS_EXTRACTION_QUEUE
                )
                LOG.info(log_json("start_manifest_processing", msg="created subs_task signature", schema=schema_name))
                # Note that the summary, hcs and subs tasks will excecutue concurrently, so ordering can't be garunteed.
                async_id = chord(report_tasks, group(summary_task, hcs_task, subs_task))()
                LOG.info(
                    log_json(
                        "start_manifest_processing",
                        msg="created chord with group",
                        async_id=str(async_id),
                        schema=schema_name,
                    )
                )
            else:
                async_id = group(report_tasks)()

            LOG.info(log_json(tracing_id, msg=f"Manifest Processing Async ID: {async_id}", schema=schema_name))

        return manifest_list, reports_tasks_queued

    def prepare(self):
        """
        Select the correct prepare function based on source type for processing each account.

        """
        providers = self.get_polling_batch()
        if not providers:
            LOG.info(log_json(msg="no accounts to be polled"))

        for provider in providers:
            LOG.info(log_json(msg="polling for account", provider_uuid=provider.uuid))

            if provider.type in [
                Provider.PROVIDER_GCP,
                Provider.PROVIDER_GCP_LOCAL,
            ]:
                self.prepare_continuous_report_sources(provider)
            else:
                self.prepare_monthly_report_sources(provider)

    def prepare_monthly_report_sources(self, provider: Provider):
        """
        Prepare processing for source types that have monthly billing reports AWS/Azure.

        Scans the database for providers that have reports that need to be processed.
        Any report it finds are queued to the appropriate celery task to download
        and process those reports.
        """
        tracing_id = provider.uuid
        account = copy.deepcopy(provider.account)
        schema = account.get("schema_name")
        accounts_labeled = False
        report_months = self.get_reports(provider.uuid)
        for month in report_months:
            LOG.info(
                log_json(
                    tracing_id,
                    msg=f"getting {month.strftime('%B %Y')} report files",
                    schema=schema,
                    provider_uuid=provider.uuid,
                )
            )
            account["report_month"] = month
            try:
                LOG.info(
                    log_json(
                        tracing_id, msg="starting manifest processing", schema=schema, provider_uuid=provider.uuid
                    )
                )
                _, reports_tasks_queued = self.start_manifest_processing(**account)
                LOG.info(
                    log_json(
                        tracing_id,
                        msg=f"manifest processing tasks queued: {reports_tasks_queued}",
                        schema=schema,
                        provider_uuid=provider.uuid,
                    )
                )

                # update labels
                if reports_tasks_queued and not accounts_labeled:
                    if provider.type not in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                        continue
                    LOG.info(
                        log_json(
                            tracing_id,
                            msg="updating account aliases",
                            schema=schema,
                            provider_uuid=provider.uuid,
                        )
                    )
                    update_account_aliases(provider)
                    LOG.info(
                        log_json(
                            tracing_id,
                            msg="done updating account aliases",
                            schema=schema,
                            provider_uuid=provider.uuid,
                        )
                    )

            except ReportDownloaderError as err:
                LOG.warning(f"Unable to download manifest for provider: {provider.uuid}. Error: {str(err)}.")
                continue
            except Exception as err:
                # Broad exception catching is important here because any errors thrown can
                # block all subsequent account processing.
                LOG.error(f"Unexpected manifest processing error for provider: {provider.uuid}. Error: {str(err)}.")
                continue

    def prepare_continuous_report_sources(self, provider: Provider):
        """
        Prepare processing for source types that have continious reports (GCP).

        Scans the database for providers that have reports that need to be processed.
        Any report it finds are queued to the appropriate celery task to download
        and process those reports.
        """
        tracing_id = provider.uuid
        account = copy.deepcopy(provider.account)
        schema = account.get("schema_name")
        LOG.info(log_json(tracing_id, msg="getting latest report files", schema=schema, provider_uuid=provider.uuid))
        if self.ingress_reports:
            start_date = get_billing_month_start(f"{self.bill_date}01")
        else:
            start_date = self.dh.today
        account["report_month"] = start_date
        try:
            LOG.info(
                log_json(tracing_id, msg="starting manifest processing", schema=schema, provider_uuid=provider.uuid)
            )
            _, reports_tasks_queued = self.start_manifest_processing(**account)
            LOG.info(
                log_json(
                    tracing_id,
                    msg=f"manifest processing tasks queued: {reports_tasks_queued}",
                    schema=schema,
                    provider_uuid=provider.uuid,
                )
            )
        except ReportDownloaderError as err:
            LOG.warning(f"Unable to download manifest for provider: {provider.uuid}. Error: {str(err)}.")
        except Exception as err:
            # Broad exception catching is important here because any errors thrown can
            # block all subsequent account processing.
            LOG.error(f"Unexpected manifest processing error for provider: {provider.uuid}. Error: {str(err)}.")

    def remove_expired_report_data(self, simulate=False):
        """
        Remove expired report data for each account.

        Args:
            simulate (Boolean) Simulate report data removal

        Returns:
            (celery.result.AsyncResult) Async result for deletion request.

        """
        async_results = []
        schemas = defaultdict(set)
        for account in Provider.objects.get_accounts():
            # create a dict of {schema: set(provider_types)}
            schemas[account.get("schema_name")].add(account.get("provider_type"))
        for schema, provider_types in schemas.items():
            provider_types = list(provider_types)
            if Provider.PROVIDER_OCP in provider_types:
                # move OCP to the end of the list because its ForeignKeys are complicated and these should be cleaned
                # up after the cloud providers
                provider_types.remove(Provider.PROVIDER_OCP)
                provider_types.append(Provider.PROVIDER_OCP)
            for provider_type in provider_types:
                LOG.info(
                    log_json(
                        "remove_expired_report_data",
                        msg="calling remove_expired_data",
                        schema=schema,
                        provider_type=provider_type,
                    )
                )
                async_result = remove_expired_data.delay(schema_name=schema, provider=provider_type, simulate=simulate)
                LOG.info(
                    log_json(
                        "remove_expired_report_data",
                        msg="expired data removal queued",
                        schema=schema,
                        provider_type=provider_type,
                        task_id=str(async_result),
                    )
                )
                async_results.append({"schema": schema, "provider_type": provider_type, "async_id": str(async_result)})
        return async_results

    def remove_expired_trino_partitions(self, simulate=False):
        """
        Removes expired trino partitions for each account.
        """
        async_results = []
        schemas = (
            Provider.objects.order_by()
            .filter(type=Provider.PROVIDER_OCP, active=True, paused=False)
            .values_list("customer__schema_name", flat=True)
            .distinct()
        )
        for schema in schemas:
            LOG.info("Calling remove_expired_trino_partitions with account: %s", schema)
            async_result = remove_expired_trino_partitions.delay(
                schema_name=schema,
                provider_type=Provider.PROVIDER_OCP,
                simulate=simulate,
            )

            LOG.info(
                "Expired partition removal queued - schema_name: %s, Task ID: %s",
                schema,
                str(async_result),
            )
            async_results.append(async_result)

        return async_results
