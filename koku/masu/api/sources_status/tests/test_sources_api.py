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
"""Test the Sources Status HTTP Client."""
from django.test import TestCase
from sources.koku_http_client import KokuHTTPClient
from sources.config import Config
import requests_mock
from unittest.mock import patch
from faker import Faker
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

faker = Faker()


class SourcesStatusTest(TestCase):
    """Test Sources Status API"""
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
        expected_uuid = '76aa76b9-d4c7-4272-a583-29f4b258fa37'
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   status_code=201,
                   json={'uuid': expected_uuid})
            response = client.create_provider(self.name, self.provider_type, self.authentication, self.billing_source)
            self.assertEqual(response.get('uuid'), expected_uuid)
            print(response.get('uuid'))
            print(response)

    def testEndpoint200Response(self):
        """Test that the sources_status list View returns 200 OK."""
        url = reverse('sources_status-list')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_http_endpoint(self):
        """
        Test sources status returns true
        """
        # 200 OK page for sources-list

        url = reverse('sources_status-list')
        client = APIClient()
        response = client.get(url + '?source-id=1')
        actualStatus = response.data['data'][0]['source-status']

        expectedStatus = 'True'
        self.assertEqual(expectedStatus, actualStatus)
