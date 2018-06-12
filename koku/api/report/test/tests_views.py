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
"""Test the Report views."""
from django.urls import reverse
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer, User
from api.report.view import process_query_parameters


class ReportViewTest(IamTestCase):
    """Tests the provider view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        for customer in self.customer_data:
            response = self.create_customer(customer)
            self.assertEqual(response.status_code, 201)

    def tearDown(self):
        """Tear down user tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()

    def test_get_costs_anon(self):
        """Test costs reports fail with an anonymous user."""
        url = reverse('reports-costs')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_get_inventory_anon(self):
        """Test inventory reports fail with an anonymous user."""
        url = reverse('reports-inventory')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_get_costs_customer_owner(self):
        """Test costs reports runs with a customer owner."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-costs')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertEqual(json_result.get('data'), [])

    def test_get_inventory_customer_owner(self):
        """Test inventory reports runs with a customer owner."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-inventory')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertEqual(json_result.get('data'), [])

    def test_process_query_parameters(self):
        """Test processing of valid parameters."""
        qs = 'group_by%5Baccount%5D=account1&filter%5Bresolution%5D=daily'
        valid, query_dict = process_query_parameters(qs)
        self.assertTrue(valid)
        self.assertEqual(query_dict.get('group_by'), {'account': ['account1']})
        self.assertEqual(query_dict.get('filter'), {'resolution': 'daily'})

    def test_process_query_parameters_invalid(self):
        """Test processing of invalid parameters."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        valid, _ = process_query_parameters(qs)
        self.assertFalse(valid)

    def test_get_costs_invalid_query_param(self):
        """Test costs reports runs with an invalid query param."""
        token = self.get_customer_owner_token(self.customer_data[0])
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-costs') + '?' + qs
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 400)
        json_result = response.json()
        self.assertEqual(json_result.get('data'), [])

    def test_get_inventory_invalid_query_param(self):
        """Test inventory reports runs with an invalid query param."""
        token = self.get_customer_owner_token(self.customer_data[0])
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-inventory') + '?' + qs
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 400)
        json_result = response.json()
        self.assertEqual(json_result.get('data'), [])
