#
# Copyright 2020 Red Hat, Inc.
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
"""Removes report data from database."""
import logging

LOG = logging.getLogger(__name__)


class GCPReportDBCleanerError(Exception):
    """Raise an error during GCP report cleaning."""


class GCPReportDBCleaner:
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema

    def purge_expired_line_item(self, expired_date, provider_uuid=None, simulate=False):
        """Remove raw line item report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        # FIXME: https://issues.redhat.com/browse/COST-671
        return []

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_uuid (uuid): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        # FIXME: https://issues.redhat.com/browse/COST-671
        return []
