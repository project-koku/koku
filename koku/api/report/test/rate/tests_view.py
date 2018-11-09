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

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.rate.serializers import RateSerializer
from reporting.rate.models import Rate, TIMEUNITS


class RateViewTests(IamTestCase):
    """Test the Rate view."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        self.fake_data = {'name': self.fake.word(),
                          'description': self.fake.text(),
                          'price': round(Decimal(random.random()), 6),
                          'timeunit': random.choice(TIMEUNITS)[0],
                          'metric': self.fake.word()}

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
        test_data = {'name': self.fake.word(),
                     'description': self.fake.text(),
                     'price': round(Decimal(random.random()), 6),
                     'timeunit': random.choice(TIMEUNITS)[0],
                     'metric': self.fake.word()}

        # create a rate
        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that we can retrieve the rate
        url = reverse('rates-detail', kwargs={'pk': response.data.get('id')})
        response = client.get(url, **self.headers)

        self.assertIsNotNone(response.data.get('id'))
        self.assertEqual(test_data['name'], response.data.get('name'))
        self.assertEqual(test_data['description'],
                         response.data.get('description'))
        self.assertEqual(test_data['price'],
                         Decimal(response.data.get('price')))
        self.assertEqual(test_data['timeunit'], response.data.get('timeunit'))
        self.assertEqual(test_data['metric'], response.data.get('metric'))

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
        url = reverse('rates-detail', kwargs={'pk': rate.id})
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get('id'))
        self.assertEqual(self.fake_data['name'], response.data.get('name'))
        self.assertEqual(self.fake_data['description'],
                         response.data.get('description'))
        self.assertEqual(self.fake_data['price'],
                         Decimal(response.data.get('price')))
        self.assertEqual(self.fake_data['timeunit'], response.data.get('timeunit'))
        self.assertEqual(self.fake_data['metric'], response.data.get('metric'))

    def test_read_rate_invalid(self):
        """Test that reading an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'pk': random.randint(5000, 10000)})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_rate_success(self):
        """Test that we can update an existing rate."""
        test_data = {'name': self.fake.word(),
                     'description': self.fake.text(),
                     'price': round(Decimal(random.random()), 6),
                     'timeunit': random.choice(TIMEUNITS)[0],
                     'metric': self.fake.word()}

        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'pk': rate.id})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(rate.id, response.data.get('id'))
        self.assertEqual(test_data['name'], response.data.get('name'))
        self.assertEqual(test_data['description'],
                         response.data.get('description'))
        self.assertEqual(test_data['price'],
                         Decimal(response.data.get('price')))
        self.assertEqual(test_data['timeunit'], response.data.get('timeunit'))
        self.assertEqual(test_data['metric'], response.data.get('metric'))

    def test_update_rate_invalid(self):
        """Test that updating an invalid rate returns an error."""
        test_data = {'name': self.fake.word(),
                     'description': self.fake.text(),
                     'price': round(Decimal(random.random()), 6),
                     'timeunit': random.choice(TIMEUNITS)[0],
                     'metric': self.fake.word()}

        url = reverse('rates-detail', kwargs={'pk': random.randint(5000, 10000)})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_success(self):
        """Test that we can delete an existing rate."""
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'pk': rate.id})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # verify the rate no longer exists
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_invalid(self):
        """Test that deleting an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'pk': random.randint(5000, 10000)})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_rate_list_success(self):
        """Test that we can read a list of rates."""
        url = reverse('rates-list')
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['count', 'next', 'previous', 'results']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('results'), list)
        self.assertEqual(len(response.data.get('results')), 1)

        rate = response.data.get('results')[0]
        self.assertIsNotNone(rate.get('id'))
        self.assertEqual(self.fake_data['name'], rate.get('name'))
        self.assertEqual(self.fake_data['description'], rate.get('description'))
        self.assertEqual(self.fake_data['price'], Decimal(rate.get('price')))
        self.assertEqual(self.fake_data['timeunit'], rate.get('timeunit'))
        self.assertEqual(self.fake_data['metric'], rate.get('metric'))
