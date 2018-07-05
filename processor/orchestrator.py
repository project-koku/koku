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
from masu.processor.tasks.download import get_report_files

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class Orchestrator():
    """
    Orchestrator for report processing.

    Top level object which is responsible for:
    * Maintaining a current list of accounts
    * Ensuring that reports are downloaded and processed for all accounts.

    """

    def __init__(self):
        """
        Orchestrator for processing.

        Args:
            None
        """
        self._accounts = AccountsAccessor().get_accounts()
        self._processing_requests = []

    def prepare(self):
        """
        Prepare a processing request for each account.

        Args:
            None

        Returns:
            None.

        """
        reports = []
        for account in self._accounts:
            credentials = account.get_access_credential()
            source = account.get_billing_source()
            customer_name = account.get_customer()
            provider = account.get_provider_type()
            schema_name = account.get_schema_name()

            stmt = 'Download task queued for {}'.format(customer_name)
            LOG.info(stmt)

            reports = get_report_files.delay(customer_name=customer_name,
                                             access_credential=credentials,
                                             report_source=source,
                                             provider_type=provider,
                                             schema_name=schema_name)
        return reports
