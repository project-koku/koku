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

"""Test the ReportingCommonDBAccessor utility object."""
import copy
from unittest.mock import Mock


from masu.database import AWS_CUR_TABLE_MAP
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase


class ReportingCommonDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportingCommonDBAccessor object."""

    def setUp(self):
        """Set up the test class with required objects."""
        super().setUp()
        self.accessor = ReportingCommonDBAccessor()
        self.report_tables = list(AWS_CUR_TABLE_MAP.values())

    def test_initializer(self):
        """Test initializer."""
        report_common_schema = self.accessor.report_common_schema
        self.assertIsInstance(self.accessor.column_map, dict)
        self.assertTrue(
            hasattr(report_common_schema, 'reporting_common_reportcolumnmap')
        )

    def test_generate_column_map(self):
        """Assert all tables are in the column map."""
        column_map = self.accessor.generate_column_map()
        keys = column_map.keys()

        tables = copy.deepcopy(self.report_tables)
        tables.remove(AWS_CUR_TABLE_MAP['cost_entry'])
        tables.remove(AWS_CUR_TABLE_MAP['line_item_daily'])
        tables.remove(AWS_CUR_TABLE_MAP['line_item_daily_summary'])
        tables.remove(AWS_CUR_TABLE_MAP['tags_summary'])
        tables.remove(AWS_CUR_TABLE_MAP['ocp_on_aws_daily_summary'])
        tables.remove(AWS_CUR_TABLE_MAP['ocp_on_aws_project_daily_summary'])
        for table in tables:
            self.assertIn(table, keys)

    def test_add(self):
        """Test the add() function."""
        with ReportingCommonDBAccessor() as accessor:
            accessor._test = Mock()
            accessor.add('test', {'foo': 'bar'})
