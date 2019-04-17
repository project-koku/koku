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
"""Test the Rate views."""

import random
from decimal import Decimal
from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from rates.models import Rate
from rates.serializers import RateSerializer


class RateViewTests(IamTestCase):
    """Test the Rate view."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        request = self.request_context['request']
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

        provider_data = {'name': 'test_provider',
                         'type': Provider.PROVIDER_OCP,
                         'authentication': {
                             'provider_resource_name': self.fake.word()
                         }}
        serializer = ProviderSerializer(data=provider_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            self.provider = serializer.save()

        self.fake_data = {'provider_uuid': self.provider.uuid,
                          'metric': Rate.METRIC_MEM_GB_USAGE_HOUR,
                          'tiered_rate': [{
                              'value': round(Decimal(random.random()), 6),
                              'unit': 'USD',
                              'usage_start': None,
                              'usage_end': None
                          }]
                          }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=self.fake_data, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def tearDown(self):
        """Tear down rate view tests."""
        with tenant_context(self.tenant):
            Rate.objects.all().delete()

    def test_create_rate_success(self):
        """Test that we can create a rate."""
        test_data = {'provider_uuid': self.provider.uuid,
                     'metric': Rate.METRIC_CPU_CORE_USAGE_HOUR,
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage_start': None,
                         'usage_end': None
                     }]
                     }

        # create a rate
        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that we can retrieve the rate
        url = reverse('rates-detail', kwargs={'uuid': response.data.get('uuid')})
        response = client.get(url, **self.headers)

        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('provider_uuid'))
        self.assertEqual(test_data['metric'], response.data.get('metric').get('name'))
        self.assertIsNotNone(response.data.get('tiered_rate'))

    def test_create_rate_invalid(self):
        """Test that creating an invalid rate returns an error."""
        test_data = {'name': self.fake.word(),
                     'description': self.fake.text(),
                     'price': round(Decimal(random.random()), 6),
                     'timeunit': 'jiffy',
                     'metric': self.fake.word()}

        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_rate_success(self):
        """Test that we can read a rate."""
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('provider_uuid'))
        self.assertEqual(self.fake_data['metric'], response.data.get('metric').get('name'))
        self.assertIsNotNone(response.data.get('tiered_rate'))

    def test_read_rate_invalid(self):
        """Test that reading an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_rate_success(self):
        """Test that we can update an existing rate."""
        test_data = self.fake_data
        test_data['tiered_rate'][0]['value'] = round(Decimal(random.random()), 6)

        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIsNotNone(response.data.get('uuid'))
        self.assertEqual(test_data['tiered_rate'][0]['value'],
                         response.data.get('tiered_rate')[0].get('value'))
        self.assertEqual(test_data['metric'], response.data.get('metric').get('name'))

    def test_update_rate_invalid(self):
        """Test that updating an invalid rate returns an error."""
        test_data = self.fake_data
        test_data['tiered_rate'][0]['value'] = round(Decimal(random.random()), 6)

        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_success(self):
        """Test that we can delete an existing rate."""
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # verify the rate no longer exists
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_invalid(self):
        """Test that deleting an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_rate_list_success(self):
        """Test that we can read a list of rates."""
        url = reverse('rates-list')
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        rate = response.data.get('data')[0]
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('provider_uuid'))
        self.assertEqual(self.fake_data['metric'], rate.get('metric').get('name'))

    def test_read_rate_list_success_provider_query(self):
        """Test that we can read a list of rates for a specific provider uuid."""
        url = '{}?provider_uuid={}'.format(reverse('rates-list'), self.provider.uuid)
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        rate = response.data.get('data')[0]
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('provider_uuid'))
        self.assertEqual(self.fake_data['metric'], rate.get('metric').get('name'))

    def test_read_rate_list_failure_provider_query(self):
        """Test that we throw proper error for invalid provider_uuid query."""
        url = '{}?provider_uuid={}'.format(reverse('rates-list'), 'not_a_uuid')

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIsNotNone(response.data.get('errors'))
