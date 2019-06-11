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
from unittest.mock import Mock, patch

from sqlalchemy.orm.session import Session

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase


class ReportingCommonDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportingCommonDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.accessor = ReportingCommonDBAccessor()
        cls.report_tables = list(AWS_CUR_TABLE_MAP.values())

    @classmethod
    def tearDownClass(cls):
        """Close the DB session."""
        cls.accessor.close_session()

    def test_initializer(self):
        """Test initializer."""
        report_common_schema = self.accessor.report_common_schema
        self.assertIsNotNone(self.accessor._session)
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

    def test_create_session(self):
        """Test the session factory and scoped session."""
        session = self.accessor._session
        new_session = self.accessor._create_session()

        self.assertIsInstance(session, Session)
        self.assertIs(session, new_session)

    def test_add(self):
        """Test the add() function."""
        mock_session = Mock(spec=Session)
        accessor = copy.copy(self.accessor)
        accessor._session = mock_session
        accessor._test = Mock()
        accessor.add('test', {'foo': 'bar'}, use_savepoint=False)
        mock_session.add.assert_called()

    def test_commit(self):
        """Test the commit() function."""
        mock_session = Mock(spec=Session)
        accessor = copy.copy(self.accessor)
        accessor._session = mock_session
        accessor.commit()
        mock_session.commit.assert_called()
