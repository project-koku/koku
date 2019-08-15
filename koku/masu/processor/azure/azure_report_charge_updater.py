#
# Copyright 2019 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Updates Azure report summary tables in the database with charge information."""
import logging

from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


class AzureReportChargeUpdaterError(Exception):
    """AzureReportChargeUpdater error."""


# pylint: disable=too-few-public-methods
class AzureReportChargeUpdater:
    """Class to update Azure report summary data with charge information."""

    def __init__(self, schema, provider_uuid, provider_id):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._provider_id = provider_id
        self._provider_uuid = provider_uuid
        self._schema = schema
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map

    def update_summary_charge_info(self, start_date=None, end_date=None):
        """Update the Azure summary table with the charge information.

        Args:
            start_date (str, Optional) - Start date of range to update derived cost.
            end_date (str, Optional) - End date of range to update derived cost.

        Returns
            None

        """
        LOG.debug('Starting charge calculation updates for provider: %s. Dates: %s-%s',
                  self._provider_uuid, str(start_date), str(end_date))
