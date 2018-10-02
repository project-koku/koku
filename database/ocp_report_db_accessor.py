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
"""Database accessor for OCP report data."""

import logging

from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class OCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
        """
        super().__init__(schema, column_map)
        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self.column_map = column_map

    def get_current_usage_report(self, report_id=None):
        """Get the most recent usage report object."""
        table_name = OCP_REPORT_TABLE_MAP['usage_report']
        interval_start = getattr(
            getattr(self.report_schema, table_name),
            'interval_start'
        )
        if report_id is not None:
            return self._get_db_obj_query(table_name).filter(id=report_id).first()

        return self._get_db_obj_query(table_name)\
            .order_by(interval_start.desc())\
            .first()

    def get_usage_report_before_date(self, date):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = OCP_REPORT_TABLE_MAP['usage_report']
        interval_start = getattr(
            getattr(self.report_schema, table_name),
            'interval_start'
        )
        base_query = self._get_db_obj_query(table_name)
        usage_report_query = base_query.filter(interval_start <= date)
        return usage_report_query

    def get_lineitem_query_for_reportid(self, query_report_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        report_id = getattr(
            getattr(self.report_schema, table_name),
            'id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(query_report_id == report_id)
        return line_item_query
