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

from masu.external.accounts_accessor import AccountsAccessor
from masu.processor.tasks import get_report_files

LOG = logging.getLogger(__name__)


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
        self._accounts = self.get_accounts(billing_source)
        self._processing_requests = []

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
            [CostUsageReportAccount]

        """
        all_accounts = AccountsAccessor().get_accounts()
        if billing_source:
            for account in all_accounts:
                if billing_source == account.get('billing_source'):
                    return [account]
        return all_accounts

    def prepare(self):
        """
        Prepare a processing request for each account.

        Args:
            None

        Returns:
            (celery.result.AsyncResult) Async result for download request.

        """
        async_result = None
        for account in self._accounts:
            LOG.info('Calling get_report_files with account: %s', account)
            async_result = get_report_files.delay(**account)
            LOG.info('Download queued - customer: %s, Task ID: %s',
                     account.get('customer_name'),
                     str(async_result))
        return async_result
