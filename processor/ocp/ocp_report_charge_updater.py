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
from decimal import Decimal

from masu.database.ocp_rate_db_accessor import OCPRateDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


class OCPReportChargeUpdater:
    """Class to update OCP report summary data with charge information."""

    def __init__(self, schema, provider_uuid):
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
            provider_uuid,
            ReportingCommonDBAccessor().column_map
        )

    @staticmethod
    def _value_gte(value, test):
        result = True
        if test:
            result = value >= Decimal(test)
        return result

    @staticmethod
    def _value_lte(value, test):
        result = True
        if test:
            return value <= Decimal(test)
        return result

    def _get_tier_rate(self, tier, usage):
        tier_rate = 0.0
        for bucket in tier:
            if self._value_gte(usage, bucket.get('usage_start')) and \
                    self._value_lte(usage, bucket.get('usage_end')):
                tier_rate += float(bucket.get('value'))
        return tier_rate

    def _calculate_rate(self, rates, usage):
        """Calculate rate based on usage."""
        rate = 0.0
        if rates and rates.get('fixed_rate'):
            fixed_rate = float(rates.get('fixed_rate').get('value'))
            rate += fixed_rate

        if rates and rates.get('tiered_rate'):
            tier_rate = self._get_tier_rate(rates.get('tiered_rate'), usage)
            rate += tier_rate
        return Decimal(rate)

    def _calculate_charge(self, rates, usage):
        """Calculate charge based on rate and usage."""
        charge_dictionary = {}
        for key, value in usage.items():
            rate = self._calculate_rate(rates, value)
            charge_value = value * rate if rate and usage else Decimal(0)
            charge_dictionary[key] = {'usage': value, 'charge': charge_value}
        return charge_dictionary

    def update_summary_charge_info(self):
        """Update the OCP summary table with the charge information.

        Args:
            None

        Returns
            None

        """
        LOG.info('Starting charge calculation updates.')

        cpu_usage = self._accessor.get_cpu_max_usage()
        cpu_rates = self._rate_accessor.get_cpu_core_usage_per_hour_rates()
        cpu_charge = self._calculate_charge(cpu_rates, cpu_usage)

        mem_usage = self._accessor.get_memory_max_usage()
        mem_rates = self._rate_accessor.get_memory_gb_usage_per_hour_rates()
        mem_charge = self._calculate_charge(mem_rates, mem_usage)

        self._accessor.populate_cpu_charge(cpu_charge)
        self._accessor.populate_memory_charge(mem_charge)

        self._accessor.commit()

    def close_session(self):
        """Close database connections and sessions."""
        self._accessor.close_connections()
        self._accessor.close_session()
