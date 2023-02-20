#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report Processing Orchestrator."""
import logging

from celery import chord
from celery import group

from api.common import log_json
from api.models import Provider
from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_data_from_manifest
from hcs.tasks import HCS_QUEUE
from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.account_label import AccountLabel
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.processor import disable_cloud_source_processing
from masu.processor.tasks import get_report_files
from masu.processor.tasks import GET_REPORT_FILES_QUEUE
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import summarize_reports
from masu.processor.tasks import SUMMARIZE_REPORTS_QUEUE
from masu.processor.worker_cache import WorkerCache

LOG = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(self, billing_source=None, provider_uuid=None, bill_date=None, queue_name=None, **kwargs):
        """
        Orchestrator for processing.

        Args:
            billing_source (String): Individual account to retrieve.

        """
        self.worker_cache = WorkerCache()
        self.billing_source = billing_source
        self.bill_date = bill_date
        self.provider_uuid = provider_uuid
        self.queue_name = queue_name
        self.ingress_reports = kwargs.get("ingress_reports")
        self.ingress_report_uuid = kwargs.get("ingress_report_uuid")
        self._accounts, self._polling_accounts = self.get_accounts(self.billing_source, self.provider_uuid)
        self._summarize_reports = kwargs.get("summarize_reports", True)

    @staticmethod
    def get_accounts(billing_source=None, provider_uuid=None):
        """
        Prepare a list of accounts for the orchestrator to get CUR from.

        If billing_source is not provided all accounts will be returned, otherwise
        only the account for the provided billing_source will be returned.

        Still a work in progress, but works for now.

        Args:
            billing_source (String): Individual account to retrieve.

        Returns:
            [CostUsageReportAccount] (all), [CostUsageReportAccount] (polling only)

        """
        all_accounts = []
        polling_accounts = []
        try:
            all_accounts = AccountsAccessor().get_accounts(provider_uuid)
        except AccountsAccessorError as error:
            LOG.error("Unable to get accounts. Error: %s", str(error))

        if billing_source:
            for account in all_accounts:
                if billing_source == account.get("billing_source"):
                    all_accounts = [account]

        for account in all_accounts:
            if disable_cloud_source_processing(account.get("schema_name")) and not provider_uuid:
                LOG.info(f"Cloud source processing disabled for {account.get('schema_name')}")
                continue
            else:
                if AccountsAccessor().is_polling_account(account):
                    polling_accounts.append(account)

        return all_accounts, polling_accounts

    def get_reports(self, provider_uuid):
        """
        Get months for provider to process.

        Args:
            (String) provider uuid to determine if initial setup is complete.

        Returns:
            (List) List of datetime objects.

        """
        with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
            reports_processed = provider_accessor.get_setup_complete()

        if self.bill_date:
            if self.ingress_reports:
                bill_date = self.bill_date + "01"
                return [DateAccessor().get_billing_month_start(bill_date)]
            return [DateAccessor().get_billing_month_start(self.bill_date)]

        if Config.INGEST_OVERRIDE or not reports_processed:
            number_of_months = Config.INITIAL_INGEST_NUM_MONTHS
        else:
            number_of_months = 2

        return sorted(DateAccessor().get_billing_months(number_of_months), reverse=True)

    def start_manifest_processing(  # noqa: 13
        self, customer_name, credentials, data_source, provider_type, schema_name, provider_uuid, report_month
    ):  # noqa: 13
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
            SUMMARY_QUEUE = SUMMARIZE_REPORTS_QUEUE
            REPORT_QUEUE = GET_REPORT_FILES_QUEUE
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
        # only gcp returns more than one manifest at the moment.
        manifest_list = downloader.download_manifest(report_month)
        report_tasks = []
        for manifest in manifest_list:
            tracing_id = manifest.get("assembly_id", manifest.get("request_id", "no-request-id"))
            files = manifest.get("files", [])
            filenames = []
            for file in files:
                filenames.append(file.get("local_file"))
            LOG.info(log_json(tracing_id, f"Report with manifest {tracing_id} contains the files: {filenames}"))

            if manifest:
                LOG.debug("Saving all manifest file names.")
                record_all_manifest_files(
                    manifest["manifest_id"],
                    [report.get("local_file") for report in manifest.get("files", [])],
                    tracing_id,
                )

            LOG.info(log_json(tracing_id, f"Found Manifests: {str(manifest)}"))

            report_files = manifest.get("files", [])

            last_report_index = len(report_files) - 1
            for i, report_file_dict in enumerate(report_files):
                local_file = report_file_dict.get("local_file")
                report_file = report_file_dict.get("key")

                # Check if report file is complete or in progress.
                if record_report_status(manifest["manifest_id"], local_file, "no_request"):
                    LOG.info(log_json(tracing_id, f"{local_file} was already processed"))
                    continue

                cache_key = f"{provider_uuid}:{report_file}"
                if self.worker_cache.task_is_running(cache_key):
                    LOG.info(log_json(tracing_id, f"{local_file} process is in progress"))
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
                        Provider.PROVIDER_OCI,
                        Provider.PROVIDER_OCI_LOCAL,
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
                    assembly_id = manifest.get("assembly_id", None)
                    if assembly_id and not self.ingress_reports:
                        report_month = assembly_id.split("|")[0]
                # add the tracing id to the report context
                # This defaults to the celery queue
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
                        ingress_reports=self.ingress_reports,
                    ).set(queue=REPORT_QUEUE)
                )
                LOG.info(log_json(tracing_id, f"Download queued - schema_name: {schema_name}."))

        manifest_list = [manifest.get("manifest_id") for manifest in manifest_list]
        if report_tasks:
            if self._summarize_reports:
                reports_tasks_queued = True
                hcs_task = collect_hcs_report_data_from_manifest.s().set(queue=HCS_Q)
                summary_task = summarize_reports.s(
                    manifest_list=manifest_list, ingress_report_uuid=self.ingress_report_uuid
                ).set(queue=SUMMARY_QUEUE)
                async_id = chord(report_tasks, group(summary_task, hcs_task))()
            else:
                async_id = group(report_tasks)()
            LOG.info(log_json(tracing_id, f"Manifest Processing Async ID: {async_id}"))

        return manifest_list, reports_tasks_queued

    def prepare(self):
        """
        Select the correct prepare function based on source type for processing each account.

        """
        for account in self._polling_accounts:
            provider_uuid = account.get("provider_uuid")
            with ProviderDBAccessor(provider_uuid) as provider_accessor:
                provider_type = provider_accessor.get_type()

            if provider_type in [
                Provider.PROVIDER_OCI,
                Provider.PROVIDER_OCI_LOCAL,
                Provider.PROVIDER_GCP,
                Provider.PROVIDER_GCP_LOCAL,
            ]:
                self.prepare_continious_report_sources(account, provider_uuid)
            else:
                self.prepare_monthly_report_sources(account, provider_uuid)

    def prepare_monthly_report_sources(self, account, provider_uuid):
        """
        Prepare processing for source types that have monthly billing reports AWS/Azure.

        Scans the database for providers that have reports that need to be processed.
        Any report it finds are queued to the appropriate celery task to download
        and process those reports.

        Args:
            None

        Returns:
            (celery.result.AsyncResult) Async result for download request.
        """
        accounts_labeled = False
        report_months = self.get_reports(provider_uuid)
        for month in report_months:
            LOG.info("Getting %s report files for account (provider uuid): %s", month.strftime("%B %Y"), provider_uuid)
            account["report_month"] = month
            try:
                _, reports_tasks_queued = self.start_manifest_processing(**account)
            except ReportDownloaderError as err:
                LOG.warning(f"Unable to download manifest for provider: {provider_uuid}. Error: {str(err)}.")
                continue
            except Exception as err:
                # Broad exception catching is important here because any errors thrown can
                # block all subsequent account processing.
                LOG.error(f"Unexpected manifest processing error for provider: {provider_uuid}. Error: {str(err)}.")
                continue

            # update labels
            if reports_tasks_queued and not accounts_labeled:
                LOG.info("Running AccountLabel to get account aliases.")
                labeler = AccountLabel(
                    auth=account.get("credentials"),
                    schema=account.get("schema_name"),
                    provider_type=account.get("provider_type"),
                )
                account_number, label = labeler.get_label_details()
                accounts_labeled = True
                if account_number:
                    LOG.info("Account: %s Label: %s updated.", account_number, label)

        return

    def prepare_continious_report_sources(self, account, provider_uuid):
        """
        Prepare processing for source types that have continious reports GCP/OCI.

        Scans the database for providers that have reports that need to be processed.
        Any report it finds are queued to the appropriate celery task to download
        and process those reports.

        Args:
            None

        Returns:
            (celery.result.AsyncResult) Async result for download request.
        """
        LOG.info("Getting latest report files for account (provider uuid): %s", provider_uuid)
        dh = DateHelper()
        start_date = dh.today
        account["report_month"] = start_date
        try:
            _, reports_tasks_queued = self.start_manifest_processing(**account)
            LOG.info("Completed latest report files for account (provider uuid): %s", provider_uuid)
        except ReportDownloaderError as err:
            LOG.warning(f"Unable to download manifest for provider: {provider_uuid}. Error: {str(err)}.")
        except Exception as err:
            # Broad exception catching is important here because any errors thrown can
            # block all subsequent account processing.
            LOG.error(f"Unexpected manifest processing error for provider: {provider_uuid}. Error: {str(err)}.")

        return

    def remove_expired_report_data(self, simulate=False):
        """
        Remove expired report data for each account.

        Args:
            simulate (Boolean) Simulate report data removal

        Returns:
            (celery.result.AsyncResult) Async result for deletion request.

        """
        async_results = []
        for account in self._accounts:
            LOG.info("Calling remove_expired_data with account: %s", account)
            async_result = remove_expired_data.delay(
                schema_name=account.get("schema_name"), provider=account.get("provider_type"), simulate=simulate
            )
            LOG.info(
                "Expired data removal queued - schema_name: %s, Task ID: %s",
                account.get("schema_name"),
                str(async_result),
            )
            async_results.append({"customer": account.get("customer_name"), "async_id": str(async_result)})
        return async_results
