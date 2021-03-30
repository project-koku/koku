#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Report Processing Orchestrator."""
import logging

from celery import chord

from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.account_label import AccountLabel
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.processor.tasks import get_report_files
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import summarize_reports
from masu.processor.worker_cache import WorkerCache

LOG = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(self, billing_source=None, provider_uuid=None, bill_date=None):
        """
        Orchestrator for processing.

        Args:
            billing_source (String): Individual account to retrieve.

        """
        self._accounts, self._polling_accounts = self.get_accounts(billing_source, provider_uuid)
        self.worker_cache = WorkerCache()
        self.bill_date = bill_date

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
            return [DateAccessor().get_billing_month_start(self.bill_date)]

        if Config.INGEST_OVERRIDE or not reports_processed:
            number_of_months = Config.INITIAL_INGEST_NUM_MONTHS
        else:
            number_of_months = 2

        return sorted(DateAccessor().get_billing_months(number_of_months), reverse=True)

    def start_manifest_processing(
        self, customer_name, credentials, data_source, provider_type, schema_name, provider_uuid, report_month
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
            (Boolaen) - Whether we are processing this manifest
        """
        reports_tasks_queued = False
        downloader = ReportDownloader(
            customer_name=customer_name,
            credentials=credentials,
            data_source=data_source,
            provider_type=provider_type,
            provider_uuid=provider_uuid,
            report_name=None,
        )
        manifest = downloader.download_manifest(report_month)

        if manifest:
            LOG.info("Saving all manifest file names.")
            record_all_manifest_files(
                manifest["manifest_id"], [report.get("local_file") for report in manifest.get("files", [])]
            )

        LOG.info(f"Found Manifests: {str(manifest)}")
        report_files = manifest.get("files", [])
        report_tasks = []
        for report_file_dict in report_files:
            local_file = report_file_dict.get("local_file")
            report_file = report_file_dict.get("key")

            # Check if report file is complete or in progress.
            if record_report_status(manifest["manifest_id"], local_file, "no_request"):
                LOG.info(f"{local_file} was already processed")
                continue

            cache_key = f"{provider_uuid}:{report_file}"
            if self.worker_cache.task_is_running(cache_key):
                LOG.info(f"{local_file} process is in progress")
                continue

            report_context = manifest.copy()
            report_context["current_file"] = report_file
            report_context["local_file"] = local_file
            report_context["key"] = report_file

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
                )
            )
            LOG.info("Download queued - schema_name: %s.", schema_name)

        if report_tasks:
            reports_tasks_queued = True
            async_id = chord(report_tasks, summarize_reports.s())()
            LOG.info(f"Manifest Processing Async ID: {async_id}")
        return manifest, reports_tasks_queued

    def prepare(self):
        """
        Prepare a processing request for each account.

        Scans the database for providers that have reports that need to be processed.
        Any report it finds is queued to the appropriate celery task to download
        and process those reports.

        Args:
            None

        Returns:
            (celery.result.AsyncResult) Async result for download request.

        """
        for account in self._polling_accounts:
            accounts_labeled = False
            provider_uuid = account.get("provider_uuid")
            report_months = self.get_reports(provider_uuid)
            for month in report_months:
                LOG.info(
                    "Getting %s report files for account (provider uuid): %s", month.strftime("%B %Y"), provider_uuid
                )
                account["report_month"] = month
                try:
                    _, reports_tasks_queued = self.start_manifest_processing(**account)
                except ReportDownloaderError as err:
                    LOG.warning(f"Unable to download manifest for provider: {provider_uuid}. Error: {str(err)}.")
                    continue
                except Exception as err:
                    # Broad exception catching is important here because any errors thrown can
                    # block all subsequent account processing.
                    LOG.error(
                        f"Unexpected manifest processing error for provider: {provider_uuid}. Error: {str(err)}."
                    )
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

    def remove_expired_report_data(self, simulate=False, line_items_only=False):
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
                schema_name=account.get("schema_name"),
                provider=account.get("provider_type"),
                simulate=simulate,
                line_items_only=line_items_only,
            )
            LOG.info(
                "Expired data removal queued - schema_name: %s, Task ID: %s",
                account.get("schema_name"),
                str(async_result),
            )
            async_results.append({"customer": account.get("customer_name"), "async_id": str(async_result)})
        return async_results
