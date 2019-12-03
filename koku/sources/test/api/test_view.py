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

"""Test the sources view."""
from base64 import b64encode
from json import dumps as json_dumps

from unittest.mock import Mock, PropertyMock
from unittest.mock import patch
from unittest import mock

import json

import requests
import requests_mock
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker

from api.provider.models import Sources
from sources.api.view import SourcesViewSet

faker = Faker()

@override_settings(ROOT_URLCONF='sources.urls')
class SourcesViewTests(TestCase):
    """Test Cases for the sources endpoint."""
    def setUp(self):
        """Setup tests."""
        super().setUp()
        self.test_account = 10001
        self.test_other_account = 10002
        self.test_source_id = 1
        self.test_offset = 1
        rh_auth = {"identity": {"account_number": str(self.test_account), "type": "User",
                   "user": {"username": "user_dev", "email": "user_dev@foo.com",
                   "is_org_admin": True}},
                   "entitlements": {"cost_management": {"is_entitled": True}}}
        json_rh_auth = json_dumps(rh_auth)
        self.rh_header = b64encode(json_rh_auth.encode('utf-8'))

        other_rh_auth = {"identity": {"account_number": str(self.test_other_account),
                         "type": "User", "user": {"username": "user_dev2",
                         "email": "user_dev2@foo.com", "is_org_admin": True}},
                         "entitlements": {"cost_management": {"is_entitled": True}}}
        json_rh_other_auth = json_dumps(other_rh_auth)
        self.other_rh_header = b64encode(json_rh_other_auth.encode('utf-8'))

        self.azure_obj = Sources(source_id=self.test_source_id,
                    auth_header=self.rh_header,
                    account_id=self.test_account,
                    offset=self.test_offset,
                    source_type='AZURE',
                    name='Test Azure Source',
                    authentication={'credentials': {'client_id': 'test_client',
                                                    'tenant_id': 'test_tenant',
                                                    'client_secret': 'test_secret'}})
        self.azure_obj.save()

        mock_url = PropertyMock(return_value='http://www.sourcesclient.com/api/v1/sources/')
        SourcesViewSet.url = mock_url

    def test_source_update(self):
        """Test the PATCH endpoint."""
        test_source_id = 1
        credentials = {'subscription_id': 'subscription-uuid'}

        with requests_mock.mock() as m:
            m.patch(f'http://www.sourcesclient.com/api/v1/sources/{test_source_id}/',
                    status_code=200, json={'credentials': credentials})

            params = {'credentials': credentials}
            url = reverse('sources-detail', kwargs={'source_id': test_source_id})

            headers={'Content-Type': 'application/json',
                     'X-Rh-Identity': self.rh_header}
            response = self.client.patch(url, json.dumps(params),
                                        content_type='application/json',
                                        headers=headers)

            self.assertEqual(response.status_code, 200)

    def test_source_put(self):
        """Test the PUT endpoint."""
        test_source_id = 1
        credentials = {'subscription_id': 'subscription-uuid'}

        with requests_mock.mock() as m:
            m.put(f'http://www.sourcesclient.com/api/v1/sources/{test_source_id}/',
                  status_code=200, json={'credentials': credentials})

            params = {'credentials': credentials}
            url = reverse('sources-detail', kwargs={'source_id': test_source_id})

            headers={'Content-Type': 'application/json',
                     'X-Rh-Identity': self.rh_header}
            response = self.client.put(url, json.dumps(params),
                                        content_type='application/json',
                                        headers=headers)

            self.assertEqual(response.status_code, 405)

    def test_source_list(self):
        """Test the LIST endpoint."""

        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/',
                    status_code=200)

            url = reverse('sources-list')

            headers={'Content-Type': 'application/json',
                     'X-Rh-Identity': self.rh_header}
            response = self.client.get(url, content_type='application/json', headers=headers)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get('meta').get('count'), 1)

    def test_source_list_other_header(self):
        """Test the LIST endpoint with other auth header."""

        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/',
                    status_code=200)

            url = reverse('sources-list')

            headers={'Content-Type': 'application/json',
                     'X-Rh-Identity': self.other_rh_header}
            import pdb; pdb.set_trace()
            response = self.client.get(url, content_type='application/json', headers=headers)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get('meta').get('count'), 0)

    def test_source_get(self):
        """Test the GET  endpoint."""
        test_source_id = 1

        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/{test_source_id}/',
                    status_code=200,
                    headers={'Content-Type': 'application/json'})

            url = reverse('sources-detail', kwargs={'source_id': test_source_id})

            headers={'Content-Type': 'application/json',
                     'X-Rh-Identity': self.rh_header}
            response = self.client.get(url, content_type='application/json', headers=headers)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(body)
