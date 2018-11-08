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
# pylint: skip-file

import logging

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class OCPRateDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
        """
        super().__init__(schema, column_map)
        self.column_map = column_map

    def get_cpu_usage_rate(self):
        """Get cpu usage charge."""
        cpu_charge = self.get_price('cpu') if self.get_timeunit('cpu') == 'nil' else None
        LOG.info('OCP CPU usage charge: %s', str(cpu_charge))
        return cpu_charge

    def get_memory_usage_rate(self):
        """Get the memory usage charge."""
        mem_charge = self.get_price('memory') if self.get_timeunit('memory') == 'nil' else None
        LOG.info('OCP Memory usage charge: %s', str(mem_charge))

        return mem_charge

    def get_price(self, value):
        """Get the price for a metric."""
        table_name = OCP_REPORT_TABLE_MAP['rate']
        metric = getattr(
            getattr(self.report_schema, table_name),
            'metric'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(value == metric)
        price_obj = line_item_query.first()
        return price_obj.price if price_obj else None

    def get_timeunit(self, value):
        """Get the timeunit for a metric."""
        table_name = OCP_REPORT_TABLE_MAP['rate']
        metric = getattr(
            getattr(self.report_schema, table_name),
            'metric'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(value == metric)
        timeunit_obj = line_item_query.first()
        return timeunit_obj.timeunit if timeunit_obj else None
