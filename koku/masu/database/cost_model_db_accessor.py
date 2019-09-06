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
"""Database accessor for OCP rate data."""

import logging

from django.db import connection

from masu.database.report_db_accessor_base import ReportDBAccessorBase

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class CostModelDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, provider_uuid, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
            provider_uuid (str): Provider uuid

        """
        super().__init__(schema, column_map)
        self.provider_uuid = provider_uuid
        self.column_map = column_map
        self.rates = self._make_rate_by_metric_map()

    def _get_base_entry(self):
        """Get base metric query."""
        query_sql = f"""
            SELECT cost_model_table.rates
            FROM {self.schema}.cost_model as cost_model_table
            JOIN {self.schema}.cost_model_map as map
                ON cost_model_table.uuid = map.cost_model_id
            WHERE map.provider_uuid = '{self.provider_uuid}'
            """
        with connection.cursor() as cursor:
            cursor.execute(query_sql)
            results = cursor.fetchall()

        return results[0][0] if len(results) == 1 else None

    def _make_rate_by_metric_map(self):
        """Convert the rates JSON list to a dict keyed on metric."""
        metric_rate_map = {}
        rates = self._get_base_entry()
        if not rates:
            return {}
        for rate in rates:
            metric_rate_map[rate.get('metric', {}).get('name')] = rate
        return metric_rate_map

    def get_rates(self, value):
        """Get the rates."""
        return self.rates.get(value)

    def get_cpu_core_usage_per_hour_rates(self):
        """Get cpu usage rates."""
        cpu_usage_rates = self.get_rates('cpu_core_usage_per_hour')
        LOG.info('OCP CPU usage rates: %s', str(cpu_usage_rates))
        return cpu_usage_rates

    def get_memory_gb_usage_per_hour_rates(self):
        """Get the memory usage rates."""
        mem_usage_rates = self.get_rates('memory_gb_usage_per_hour')
        LOG.info('OCP Memory usage rates: %s', str(mem_usage_rates))
        return mem_usage_rates

    def get_cpu_core_request_per_hour_rates(self):
        """Get cpu request rates."""
        cpu_request_rates = self.get_rates('cpu_core_request_per_hour')
        LOG.info('OCP CPU request rates: %s', str(cpu_request_rates))
        return cpu_request_rates

    def get_memory_gb_request_per_hour_rates(self):
        """Get the memory request rates."""
        mem_request_rates = self.get_rates('memory_gb_request_per_hour')
        LOG.info('OCP Memory request rates: %s', str(mem_request_rates))
        return mem_request_rates

    def get_storage_gb_usage_per_month_rates(self):
        """Get the storage usage rates."""
        storage_usage_rates = self.get_rates('storage_gb_usage_per_month')
        LOG.info('OCP Storage usage rates: %s', str(storage_usage_rates))
        return storage_usage_rates

    def get_storage_gb_request_per_month_rates(self):
        """Get the storage request rates."""
        storage_request_rates = self.get_rates('storage_gb_request_per_month')
        LOG.info('OCP Storage request rates: %s', str(storage_request_rates))
        return storage_request_rates
