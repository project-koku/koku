#
# Copyright 2018 Red Hat, Inc.
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
"""Updates report summary tables in the database with charge information."""

import logging

from masu.database.ocp_rate_db_accessor import OCPRateDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


class OCPReportChargeUpdater:
    """Class to update OCP report summary data with charge information."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._accessor = OCPReportDBAccessor(
            schema,
            ReportingCommonDBAccessor().column_map
        )
        self._rate_accessor = OCPRateDBAccessor(
            schema,
            ReportingCommonDBAccessor().column_map
        )

    def update_summary_charge_info(self):
        """Update the OCP summary table with the charge information.

        Args:
            None

        Returns
            None

        """
        LOG.info('Starting charge calculation updates.')
        cpu_charge = self._rate_accessor.get_cpu_usage_rate()
        mem_charge = self._rate_accessor.get_memory_usage_rate()

        if cpu_charge:
            self._accessor.populate_cpu_charge(cpu_charge)

        if mem_charge:
            self._accessor.populate_memory_charge(mem_charge)

        self._accessor.commit()

    def close_session(self):
        """Close database connections and sessions."""
        self._accessor.close_connections()
        self._accessor.close_session()
