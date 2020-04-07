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

    def test_add(self):
        """Test the add() function."""
        with ReportingCommonDBAccessor() as accessor:
            accessor._test = Mock()
            accessor.add("test", {"foo": "bar"})
