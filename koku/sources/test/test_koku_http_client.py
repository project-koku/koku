#
# Copyright 2019 Red Hat, Inc.
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
"""Test the Koku HTTP Client."""
from unittest.mock import patch

import requests
import requests_mock
from django.test import TestCase
from faker import Faker
from sources.config import Config
from sources.koku_http_client import KokuHTTPClient, KokuHTTPClientError, KokuHTTPClientNonRecoverableError

faker = Faker()


class KokuHTTPClientTest(TestCase):
    """Test cases for KokuHTTPClient."""

    def setUp(self):
        """Test case setup."""
        super().setUp()
        self.name = 'Test Provider'
        self.provider_type = 'PVD'
        self.authentication = 'testauth'
        self.billing_source = 'testbillingsource'

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_create_provider(self):
        """Test to create a provider."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        expected_uuid = faker.uuid4()
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   status_code=201,
                   json={'uuid': expected_uuid})
            response = client.create_provider(self.name, self.provider_type, self.authentication, self.billing_source)
            self.assertEqual(response.get('uuid'), expected_uuid)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_create_provider_exceptions(self):
        """Test to create a provider with a non-recoverable error."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   status_code=400,
                   json={'uuid': faker.uuid4()})
            with self.assertRaises(KokuHTTPClientNonRecoverableError):
                client.create_provider(self.name, self.provider_type, self.authentication, self.billing_source)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_create_provider_connection_error(self):
        """Test to create a provider with a connection error."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   exc=requests.exceptions.RequestException)
            with self.assertRaises(KokuHTTPClientError):
                client.create_provider(self.name, self.provider_type, self.authentication, self.billing_source)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_destroy_provider(self):
        """Test to destroy a provider."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        expected_uuid = faker.uuid4()
        with requests_mock.mock() as m:
            m.delete(f'http://www.koku.com/api/cost-management/v1/providers/{expected_uuid}/',
                     status_code=204)
            response = client.destroy_provider(expected_uuid)
            self.assertEqual(response.status_code, 204)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_destroy_provider_exception(self):
        """Test to destroy a provider with a connection error."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        expected_uuid = faker.uuid4()
        with requests_mock.mock() as m:
            m.delete(f'http://www.koku.com/api/cost-management/v1/providers/{expected_uuid}/',
                     exc=requests.exceptions.RequestException)
            with self.assertRaises(KokuHTTPClientError):
                client.destroy_provider(expected_uuid)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_destroy_provider_error(self):
        """Test to destroy a provider with a koku server error."""
        client = KokuHTTPClient(auth_header=Config.SOURCES_FAKE_HEADER)
        expected_uuid = faker.uuid4()
        with requests_mock.mock() as m:
            m.delete(f'http://www.koku.com/api/cost-management/v1/providers/{expected_uuid}/',
                     status_code=400)
            with self.assertRaises(KokuHTTPClientError):
                client.destroy_provider(expected_uuid)
