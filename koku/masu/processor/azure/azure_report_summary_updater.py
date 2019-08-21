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
"""Updates report summary tables in the database."""
import logging

from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class AzureReportSummaryUpdater:
    """Class to update AWS report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema_name = schema
        self._provider = provider
        self._manifest = manifest
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map
        self._date_accessor = DateAccessor()

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str): A start date and end date.

        """
        LOG.info('update_daily_tables for: %s-%s', str(start_date), str(end_date))
        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        LOG.info('update_summary_tables for: %s-%s', str(start_date), str(end_date))
        return start_date, end_date
