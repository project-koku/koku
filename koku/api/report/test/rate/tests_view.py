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
from api.report.rate.view import RateViewSet
from reporting.rate.models import Rate, TIMEUNITS

class RateViewTests(IamTestCase):
    """Test the Rate view."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        self.fake_data = {'name': self.fake.word(),
                          'description' : self.fake.text(),
                          'price': round(Decimal(random.random()), 6),
                          'timeunit': random.choice(TIMEUNITS)[0],
                          'metric': self.fake.word()}

        with tenant_context(self.tenant):
            serializer = RateSerializer(data=self.fake_data, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_create_rate(self):
        url = reverse('rates-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # TODO: check response contents

    def test_read_rate(self):
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'id': rate.id})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # TODO: check response contents

    def test_update_rate(self):
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'id': rate.id})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # TODO: check response contents

    def test_delete_rate(self):
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'id': rate.id})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # TODO: check response contents
