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
import masu.processor.tasks.process as process_task
from masu.external.accounts_accessor import AccountsAccessor
from masu.processor.cur_process_request import CURProcessRequest

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
            None
        """
        self._accounts = AccountsAccessor().get_accounts()
        self._processing_requests = []

    def prepare_curs(self):
        """
        Prepare a CUR processing request for each account.

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

            stmt = 'Download task queued for {}'.format(customer_name)
            LOG.info(stmt)

            reports = download_task.get_report_files(customer_name=customer_name,
                                                     access_credential=credentials,
                                                     report_source=source,
                                                     provider_type=provider)
            for report_dict in reports:
                cur_request = CURProcessRequest()
                cur_request.schema_name = account.get_schema_name()
                cur_request.report_path = report_dict.get('file')
                cur_request.compression = report_dict.get('compression')

                self._processing_requests.append(cur_request)

        return reports

    def process_curs(self):
        """
        Process downloaded cost usage reports.

        Args:
            None

        Returns:
            None.

        """
        for request in self._processing_requests:
            LOG.info(str(request))
            process_task.process_report_file(request)
