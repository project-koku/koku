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
from datetime import datetime

from masu.database.provider_status_accessor import (InProgressTimeoutActions,
                                                    ProviderStatusCode)
from masu.external.account_label import AccountLabel
from masu.external.accounts_accessor import (AccountsAccessor, AccountsAccessorError)
from masu.processor.tasks import (get_report_files,
                                  remove_expired_data,
                                  summarize_reports)
from masu.providers.status import ProviderStatus

LOG = logging.getLogger(__name__)

# The maximum amount of time a provider status can be IN_PROGRESS before
# taking the INPROGRESS_TIMEOUT_ACTION
MAX_INPROGRESS_TIMEOUT_SECONDS = 43200    # 12 hours

# The behavior when a provider sits in-progress beyond the timeout value.
INPROGRESS_TIMEOUT_ACTION = InProgressTimeoutActions.SET_READY


# pylint: disable=too-few-public-methods
class Orchestrator():
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(self, billing_source=None):
        """
        Orchestrator for processing.

        Args:
            billing_source (String): Individual account to retrieve.

        """
        self._accounts, self._polling_accounts = self.get_accounts(billing_source)

    @staticmethod
    def get_accounts(billing_source=None):
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
            all_accounts = AccountsAccessor().get_accounts()
        except AccountsAccessorError as error:
            LOG.error('Unable to get accounts. Error: %s', str(error))

        if billing_source:
            for account in all_accounts:
                if billing_source == account.get('billing_source'):
                    all_accounts = [account]

        for account in all_accounts:
            if AccountsAccessor().is_polling_account(account):
                polling_accounts.append(account)

        return all_accounts, polling_accounts

    def prepare(self, task):
        """
        Prepare a processing request for each account.

        Args:
            task           (Object): bound Celery task

        Returns:
            (celery.result.AsyncResult) Async result for download request.

        """
        async_result = None
        for account in self._polling_accounts:
            provider_uuid = account.get('provider_uuid')
            provider_status = ProviderStatus(provider_uuid)
            LOG.debug('Provider Status: %s', provider_status)
            if provider_status.is_backing_off():
                LOG.info('Provider "%s" skipped: %s',
                         account.get('provider_uuid'),
                         provider_status)
                continue
            elif provider_status.is_valid():
                LOG.info('Getting report files for account (provider uuid): %s', provider_uuid)

                # set ProviderStatus to IN_PROGRESS and note the parent task ID.
                provider_status.set_status(ProviderStatusCode.IN_PROGRESS,
                                           task.request.root_id)

                async_result = (get_report_files.s(**account) | summarize_reports.s()).\
                    apply_async()

                LOG.info('Download queued - schema_name: %s, Task ID: %s',
                         account.get('schema_name'),
                         str(async_result))

                # update labels
                labeler = AccountLabel(auth=account.get('authentication'),
                                       schema=account.get('schema_name'),
                                       provider_type=account.get('provider_type'))
                account, label = labeler.get_label_details()
                if account:
                    LOG.info('Account: %s Label: %s updated.', account, label)
            elif provider_status.get_status() == int(ProviderStatusCode.IN_PROGRESS):
                msg = (f'Provider "{account.get("provider_uuid")}" skipped.'
                       ' Unable to process reports already in-progress.')
                LOG.info(msg)
                if provider_status.get_last_message() == task.request.root_id:
                    # do nothing else until a new processing task fires.
                    continue

                now_ts = datetime.now().timestamp()
                prov_ts = provider_status.get_timestamp().timestamp()
                if int(now_ts - prov_ts) > MAX_INPROGRESS_TIMEOUT_SECONDS:
                    msg = ('Provider in-progress timeout exceeded for provider '
                           f'"{account.get("provider_uuid")}". Resetting status '
                           f'to "{INPROGRESS_TIMEOUT_ACTION}". Report '
                           'processing will resume on next polling interval.')
                    LOG.info(msg)
                    provider_status.set_status(INPROGRESS_TIMEOUT_ACTION,
                                               'In-progress timeout exceeded.')
        return async_result

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
            LOG.info('Calling remove_expired_data with account: %s', account)
            async_result = remove_expired_data.delay(schema_name=account.get('schema_name'),
                                                     provider=account.get('provider_type'),
                                                     simulate=simulate)
            LOG.info('Expired data removal queued - schema_name: %s, Task ID: %s',
                     account.get('schema_name'),
                     str(async_result))
            async_results.append({'customer': account.get('customer_name'),
                                  'async_id': str(async_result)})
        return async_results
