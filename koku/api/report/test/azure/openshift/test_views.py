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
"""Test the OCP-on-Azure Report views."""

from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase


class AzureReportViewTest(IamTestCase):
    """Azure report view test cases."""

    NAMES = [
        'reports-openshift-azure-costs',
        'reports-openshift-azure-storage',
        'reports-openshift-azure-instance-type',
        # 'openshift-azure-tags',  # TODO: uncomment when we do tagging
    ]

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        query = 'delta=cost'
        url = reverse('reports-openshift-azure-costs') + '?' + query
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = 'Invalid'
        expected = f'"{bad_delta}" is not a valid choice.'
        query = f'delta={bad_delta}'
        url = reverse('reports-openshift-azure-costs') + '?' + query
        response = self.client.get(url, **self.headers)
        result = str(response.data.get('delta')[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)
