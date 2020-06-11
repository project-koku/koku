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

from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.account_label import AccountLabel
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.processor.tasks import get_report_files
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import summarize_reports
from masu.providers.status import ProviderStatus

LOG = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(self, billing_source=None, provider_uuid=None):
        """
        Orchestrator for processing.

        Args:
            billing_source (String): Individual account to retrieve.

        """
        self._accounts, self._polling_accounts = self.get_accounts(billing_source, provider_uuid)

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

    @staticmethod
    def get_reports(provider_uuid):
        """
        Get months for provider to process.

        Args:
            (String) provider uuid to determine if initial setup is complete.

        Returns:
            (List) List of datetime objects.

        """
        with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
            reports_processed = provider_accessor.get_setup_complete()

        if Config.INGEST_OVERRIDE or not reports_processed:
            number_of_months = Config.INITIAL_INGEST_NUM_MONTHS
        else:
            number_of_months = 2

        return DateAccessor().get_billing_months(number_of_months)

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
        async_result = None
        for account in self._polling_accounts:
            provider_uuid = account.get("provider_uuid")
            report_months = self.get_reports(provider_uuid)
            for month in report_months:
                provider_status = ProviderStatus(provider_uuid)
                if provider_status.is_valid() and not provider_status.is_backing_off():
                    LOG.info(
                        "Getting %s report files for account (provider uuid): %s",
                        month.strftime("%B %Y"),
                        provider_uuid,
                    )
                    account["report_month"] = month
                    async_result = (get_report_files.s(**account) | summarize_reports.s()).apply_async()

                    LOG.info(
                        "Download queued - schema_name: %s, Task ID: %s", account.get("schema_name"), str(async_result)
                    )

                    # update labels
                    labeler = AccountLabel(
                        auth=account.get("authentication"),
                        schema=account.get("schema_name"),
                        provider_type=account.get("provider_type"),
                    )
                    account_number, label = labeler.get_label_details()
                    if account_number:
                        LOG.info("Account: %s Label: %s updated.", account_number, label)
                else:
                    LOG.info(
                        "Provider skipped: %s Valid: %s Backing off: %s",
                        account.get("provider_uuid"),
                        provider_status.is_valid(),
                        provider_status.is_backing_off(),
                    )
        return async_result

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
