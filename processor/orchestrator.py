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

import masu.processor.tasks.download as download_task
from masu.external.accounts_accessor import AccountsAccessor

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class Orchestrator():
    """
    Orchestrator for CUR processing.

    Top level object which is responsible for:
    * Maintaining a current list of CUR accounts
    * Ensuring that CUR reports are downloaded and processed for all accounts.

    """

    def __init__(self):
        """
        Orchestrator for CUR processing.

        Args:
            download_path (String) filesystem path to store downloaded files
        """
        self._accounts = AccountsAccessor().get_accounts()

    def download_curs(self):
        """
        Download CUR for each account.

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
            provider = account.get_provider()

            stmt = 'Download task queued for {}'.format(customer_name)
            LOG.info(stmt)

            reports = download_task.get_report_files(customer_name=customer_name,
                                                     access_credential=credentials,
                                                     report_source=source,
                                                     provider_type=provider)

        return reports
