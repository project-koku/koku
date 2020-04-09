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
"""Test Reporting Common."""
import copy
import unittest

from masu.database import AWS_CUR_TABLE_MAP
from reporting_common import REPORT_COLUMN_MAP


class TestReportingCommon(unittest.TestCase):
    """Test Reporting Common."""

    def setUp(self):
        """Set up the test class with required objects."""
        self.report_tables = list(AWS_CUR_TABLE_MAP.values())

    def test_generate_column_map(self):
        """Assert all tables are in the column map."""
        keys = REPORT_COLUMN_MAP.keys()

        tables = copy.deepcopy(self.report_tables)
        tables.remove(AWS_CUR_TABLE_MAP["cost_entry"])
        tables.remove(AWS_CUR_TABLE_MAP["line_item_daily"])
        tables.remove(AWS_CUR_TABLE_MAP["line_item_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["tags_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"])
        tables.remove(AWS_CUR_TABLE_MAP["ocp_on_aws_tags_summary"])
        for table in tables:
            self.assertIn(table, keys)
