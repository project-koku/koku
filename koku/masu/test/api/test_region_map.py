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
"""Test the region map endpoint."""

from unittest.mock import patch

from django.test import TestCase

from masu.test.util.aws.test_region_map import MockResponse, TEST_HTML


class RegionMapAPIViewTest(TestCase):
    """Test Cases for the Region Map API."""

    @classmethod
    def setUpClass(cls):
        """Set up test class with shared objects."""
        with open(TEST_HTML) as page:
            cls.test_data = page.read()

    @patch(
        'masu.database.reporting_common_db_accessor.ReportingCommonDBAccessor',
        autospec=True,
    )
    @patch('masu.util.aws.region_map.requests.get')
    def skip_test_update_region_map(self, mock_response, mock_accessor):
        """Test the region map endpoint."""
        mock_response.return_value = MockResponse(self.test_data, 200)

        response = self.client.get('/api/v1/regionmap/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'true\n')
