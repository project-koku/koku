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
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

faker = Faker()


@override_settings(ROOT_URLCONF='sources.urls')
class SourcesStatusTest(TestCase):
    """Source Status Test Class."""

    def test_http_endpoint_200_OK(self):
        """
        Test source-status endpoint returns a 200 OK.

        When we pass in a ?source_id=<integer> parameter, the endpoint should return 200 OK.
        """
        # 200 OK page for sources-list

        url = reverse('source-status')
        client = APIClient()
        response = client.get(url + '?source_id=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_http_endpoint_returns_false_(self):
        """
        Test sources status returns False.

        When there's no provider or source, the endpoint should return False
        """
        url = reverse('source-status')
        client = APIClient()
        response = client.get(url + '?source_id=1')
        actualStatus = response.data
        expectedStatus = False

        self.assertEqual(actualStatus, expectedStatus)
