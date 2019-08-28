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

"""Test the common util functions."""

import json
from datetime import datetime
from decimal import Decimal

from masu.external import (
    AMAZON_WEB_SERVICES,
    AWS_LOCAL_SERVICE_PROVIDER,
    LISTEN_INGEST,
    AZURE_LOCAL_SERVICE_PROVIDER,
    OPENSHIFT_CONTAINER_PLATFORM,
    POLL_INGEST,
)
import masu.util.common as common_utils

from masu.test import MasuTestCase


class CommonUtilTests(MasuTestCase):
    def test_extract_uuids_from_string(self):
        """Test that a uuid is extracted from a string."""

        assembly_id = '882083b7-ea62-4aab-aa6a-f0d08d65ee2b'
        cur_key = '/koku/20180701-20180801/{}/koku-1.csv.gz'.format(assembly_id)

        uuids = common_utils.extract_uuids_from_string(cur_key)
        self.assertEqual(len(uuids), 1)
        self.assertEqual(uuids.pop(), assembly_id)

    def test_extract_uuids_from_string_capitals(self):
        """Test that a uuid is extracted from a string with capital letters."""

        assembly_id = '882083B7-EA62-4AAB-aA6a-f0d08d65Ee2b'
        cur_key = '/koku/20180701-20180801/{}/koku-1.csv.gz'.format(assembly_id)

        uuids = common_utils.extract_uuids_from_string(cur_key)
        self.assertEqual(len(uuids), 1)
        self.assertEqual(uuids.pop(), assembly_id)

    def test_stringify_json_data_list(self):
        """Test that each element of JSON is returned as a string."""
        data = [
            {'datetime': datetime.utcnow(), 'float': 1.2, 'int': 1, 'str': 'string'},
            {'Decimal': Decimal('1.2')},
        ]

        with self.assertRaises(TypeError):
            json.dumps(data)

        result = common_utils.stringify_json_data(data)

        self.assertIsInstance(result[0]['datetime'], str)
        self.assertIsInstance(result[0]['float'], str)
        self.assertIsInstance(result[0]['int'], str)
        self.assertIsInstance(result[0]['str'], str)
        self.assertIsInstance(result[1]['Decimal'], str)

    def test_stringify_json_data_dict(self):
        """Test that the dict block is covered."""
        data = {
            'datetime': datetime.utcnow(),
            'float': 1.2,
            'int': 1,
            'str': 'string',
            'Decimal': Decimal('1.2'),
        }

        with self.assertRaises(TypeError):
            json.dumps(data)

        result = common_utils.stringify_json_data(data)

        self.assertIsInstance(result['datetime'], str)
        self.assertIsInstance(result['float'], str)
        self.assertIsInstance(result['int'], str)
        self.assertIsInstance(result['str'], str)
        self.assertIsInstance(result['Decimal'], str)

    def test_ingest_method_type(self):
        """Test taht the correct ingest method is returned for provider type."""
        test_matrix = [
            {'provider_type': AMAZON_WEB_SERVICES, 'expected_ingest': POLL_INGEST},
            {
                'provider_type': AWS_LOCAL_SERVICE_PROVIDER,
                'expected_ingest': POLL_INGEST,
            },
            {
                'provider_type': OPENSHIFT_CONTAINER_PLATFORM,
                'expected_ingest': LISTEN_INGEST,
            },
            {
                'provider_type': AZURE_LOCAL_SERVICE_PROVIDER,
                'expected_ingest': POLL_INGEST,
            },
            {'provider_type': 'NEW_TYPE', 'expected_ingest': None},
        ]

        for test in test_matrix:
            ingest_method = common_utils.ingest_method_for_provider(
                test.get('provider_type')
            )
            self.assertEqual(ingest_method, test.get('expected_ingest'))
