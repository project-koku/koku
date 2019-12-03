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
import json
from unittest.mock import PropertyMock

import requests_mock
from django.test.utils import override_settings
from django.urls import reverse
from sources.api.view import SourcesViewSet

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Sources


@override_settings(ROOT_URLCONF='sources.urls')
class SourcesViewTests(IamTestCase):
    """Test Cases for the sources endpoint."""
    def setUp(self):
        """Setup tests."""
        super().setUp()
        self.test_account = '10001'
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                            is_admin=False)
        self.test_other_account = 10002
        self.test_source_id = 1

        self.azure_obj = Sources(source_id=self.test_source_id,
                                 auth_header=self.request_context['request'].META,
                                 account_id=customer.get('account_id'),
                                 offset=1,
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
        credentials = {'subscription_id': 'subscription-uuid'}

        with requests_mock.mock() as m:
            m.patch(f'http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/',
                    status_code=200, json={'credentials': credentials})

            params = {'credentials': credentials}
            url = reverse('sources-detail', kwargs={'source_id': self.test_source_id})

            response = self.client.patch(url, json.dumps(params),
                                         content_type='application/json',
                                         **self.request_context['request'].META)

            self.assertEqual(response.status_code, 200)

    def test_source_put(self):
        """Test the PUT endpoint."""
        credentials = {'subscription_id': 'subscription-uuid'}

        with requests_mock.mock() as m:
            m.put(f'http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/',
                  status_code=200, json={'credentials': credentials})

            params = {'credentials': credentials}
            url = reverse('sources-detail', kwargs={'source_id': self.test_source_id})

            response = self.client.put(url, json.dumps(params),
                                       content_type='application/json',
                                       **self.request_context['request'].META)

            self.assertEqual(response.status_code, 405)

    def test_source_list(self):
        """Test the LIST endpoint."""

        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/',
                  status_code=200)

            url = reverse('sources-list')

            response = self.client.get(url, content_type='application/json',
                                       **self.request_context['request'].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get('meta').get('count'), 1)

    def test_source_list_other_header(self):
        """Test the LIST endpoint with other auth header not matching test data."""
        user_data = self._create_user_data()

        customer = self._create_customer_data(account='10002')
        request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                       is_admin=False)
        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/',
                  status_code=200)

            url = reverse('sources-list')

            response = self.client.get(url, content_type='application/json',
                                       **request_context['request'].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get('meta').get('count'), 0)

    def test_source_get(self):
        """Test the GET endpoint."""
        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/',
                  status_code=200,
                  headers={'Content-Type': 'application/json'})

            url = reverse('sources-detail', kwargs={'source_id': self.test_source_id})

            response = self.client.get(url, content_type='application/json',
                                       **self.request_context['request'].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(body)

    def test_source_get_other_header(self):
        """Test the GET endpoint other header not matching test data."""
        user_data = self._create_user_data()

        customer = self._create_customer_data(account='10002')
        request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                       is_admin=False)
        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/',
                  status_code=200,
                  headers={'Content-Type': 'application/json'})

            url = reverse('sources-detail', kwargs={'source_id': self.test_source_id})

            response = self.client.get(url, content_type='application/json',
                                       **request_context['request'].META)
            self.assertEqual(response.status_code, 404)

    def test_source_get_status(self):
        """Test the STATUS endpoint is accessible for any user."""
        user_data = self._create_user_data()
        customer = self._create_customer_data(account='10002')
        other_request_context = self._create_request_context(customer, user_data,
                                                             create_customer=True,
                                                             is_admin=False)

        request_contexts = [self.request_context, other_request_context]
        for context in request_contexts:
            with requests_mock.mock() as m:
                m.get(f'http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/status/',
                      status_code=200,
                      headers={'Content-Type': 'application/json'})

                base_url = reverse('sources-detail', kwargs={'source_id': self.test_source_id})
                url = base_url + 'status/'
                response = self.client.get(url, content_type='application/json',
                                           **context['request'].META)
                body = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertIn('availability_status', body.keys())
                self.assertIn('availability_status_error', body.keys())

    def test_source_status_not_found(self):
        """Test the STATUS endpoint for non existent source."""
        wrong_source_id = self.test_source_id + 1
        with requests_mock.mock() as m:
            m.get(f'http://www.sourcesclient.com/api/v1/sources/{wrong_source_id}/',
                  status_code=200,
                  headers={'Content-Type': 'application/json'})

            base_url = reverse('sources-detail', kwargs={'source_id': wrong_source_id})
            url = base_url + 'status/'
            response = self.client.get(url, content_type='application/json',
                                       **self.request_context['request'].META)
            self.assertEqual(response.status_code, 404)
