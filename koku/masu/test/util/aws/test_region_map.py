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

"""Test the region map util."""

import json
import logging
from unittest.mock import patch

from django.db import IntegrityError

import masu.util.aws.region_map as rmap
from masu.test import MasuTestCase

TEST_HTML = './koku/masu/test/data/test_region_page.html'
LOG = logging.getLogger(__name__)


class MockResponse:
    """A fake requests.Response object."""

    status_code = None
    text = None

    def __init__(self, data, status):
        self.status_code = status
        self.text = str(data)


class RegionMapTests(MasuTestCase):
    """Test the region mapping utility class."""

    @classmethod
    def setUpClass(cls):
        with open(TEST_HTML) as page:
            cls.test_data = page.read()

    @patch('masu.util.aws.region_map.requests.get')
    def test_parse_page_success(self, mock_response):
        """test successful parse_page()."""
        mock_response.return_value = MockResponse(self.test_data, 200)

        data = rmap.parse_page()
        self.assertIsNotNone(data)
        self.assertIsInstance(data, str)

        json_data = json.loads(data)
        self.assertIn('Amazon Pinpoint', json_data.keys())
        self.assertIn('Endpoint', json_data.get('Amazon Pinpoint')[0])
        self.assertIn('Endpoint', json_data.get('Amazon Pinpoint')[0])
        self.assertIn('Protocol', json_data.get('Amazon Pinpoint')[0])
        self.assertIn('Region', json_data.get('Amazon Pinpoint')[0])
        self.assertIn('Region Name', json_data.get('Amazon Pinpoint')[0])
        self.assertIsNotNone('Endpoint', json_data.get('Amazon Pinpoint')[0])
        self.assertIsNotNone('Protocol', json_data.get('Amazon Pinpoint')[0])
        self.assertIsNotNone('Region', json_data.get('Amazon Pinpoint')[0])
        self.assertIsNotNone('Region Name', json_data.get('Amazon Pinpoint')[0])

    @patch('masu.util.aws.region_map.requests.get')
    def test_parse_page_fail(self, mock_response):
        """test failed parse_page()."""
        with self.assertRaises(IOError):
            rmap.parse_page()

    def test_filter_region_string_success(self):
        """test _filter_region_string."""
        result = rmap._filter_region_string('*** test   ')
        self.assertEqual(result, 'test')

    def test_filter_region_string_filtered(self):
        """test _filter_region_string filters blacklisted values."""
        result = rmap._filter_region_string('n/a')
        self.assertIsNone(result)

    def test_get_region_map(self):
        """test get_region_map()."""
        sample = {
            'Alexa for Business': [
                {
                    'Region Name': 'US East (N. Virginia)',
                    'Region': 'us-east-1',
                    'Endpoint': 'a4b.us-east-1.amazonaws.com',
                    'Protocol': 'HTTPS',
                }
            ]
        }

        expected = {'us-east-1': 'US East (N. Virginia)'}

        result = rmap.get_region_map(sample)
        self.assertEqual(result, expected)

    @patch(
        'masu.database.reporting_common_db_accessor.ReportingCommonDBAccessor',
        autospec=True,
    )
    @patch('masu.util.aws.region_map.requests.get')
    def test_update_region_mapping_success(self, mock_response, mock_accessor):
        """test sucessful update_region_mapping()"""
        mock_common_accessor = mock_accessor().__enter__()
        mock_response.return_value = MockResponse(self.test_data, 200)
        response = rmap.update_region_mapping()
        self.assertEqual(str(response), 'True')
        mock_common_accessor.add.assert_called()

    @patch(
        'masu.database.reporting_common_db_accessor.ReportingCommonDBAccessor',
        autospec=True,
    )
    @patch('masu.util.aws.region_map.requests.get')
    def test_update_region_mapping_fail(self, mock_response, mock_accessor):
        """test sucessful update_region_mapping()"""
        mock_common_accessor = mock_accessor().__enter__()
        mock_response.return_value = MockResponse(self.test_data, 200)
        mock_common_accessor.add.side_effect = IntegrityError('fake', 'fake', 'fake')

        expected = 'WARNING:masu.util.aws.region_map:Duplicate entry in DB: "us-east-1" - "US East (N. Virginia)"'

        logging.disable(logging.NOTSET)
        with self.assertLogs('masu.util.aws.region_map', level='WARNING') as logger:
            rmap.update_region_mapping()
            self.assertIn(expected, logger.output)
