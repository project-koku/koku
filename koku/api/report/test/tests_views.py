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
from unittest.mock import Mock

from django.urls import reverse
from rest_framework.serializers import ValidationError
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer, Tenant, User
from api.report.view import get_tenant, process_query_parameters


class ReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        customer = self.customer_data[0]
        response = self.create_customer(customer)
        self.assertEqual(response.status_code, 201)
        customer_json = response.json()
        customer_uuid = customer_json.get('uuid')
        customer_obj = Customer.objects.filter(uuid=customer_uuid).get()
        self.tenant = Tenant(schema_name=customer_obj.schema_name)
        self.tenant.save()

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

    def test_get_storage_anon(self):
        """Test inventory storage reports fail with an anonymous user."""
        url = reverse('reports-storage')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_get_instance_anon(self):
        """Test inventory instance reports fail with an anonymous user."""
        url = reverse('reports-instance-type')
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
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_instance_customer_owner(self):
        """Test inventory instance reports runs with a customer owner."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-instance-type')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_storage_customer_owner(self):
        """Test inventory storage reports runs with a customer owner."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-storage')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

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

    def test_get_instance_usage_invalid_query_param(self):
        """Test instance usage reports runs with an invalid query param."""
        token = self.get_customer_owner_token(self.customer_data[0])
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-instance-type') + '?' + qs
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_get_storage_usage_invalid_query_param(self):
        """Test storage usage reports runs with an invalid query param."""
        token = self.get_customer_owner_token(self.customer_data[0])
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-storage') + '?' + qs
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_get_tenant_no_group(self):
        """Test get_tenant with a user with no group."""
        user = Mock()
        group = Mock()
        group.id = 909090
        user.groups.first.return_value = group

        with self.assertRaises(ValidationError):
            get_tenant(user)

    def test_get_costs_csv(self):
        """Test CSV output of costs reports."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-costs')
        client = APIClient()

        # kludge alert!
        #
        # APIClient.credentials() is just a dict of arbitrary headers that the
        # client ensures are set with every request.
        #
        # APIClient doesn't provide a better facility to set headers, so we're
        # abusing the interface that it does provide to get what we want.
        client.credentials(HTTP_AUTHORIZATION=token, HTTP_ACCEPT='text/csv')

        response = client.get(url)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_instance_csv(self):
        """Test CSV output of inventory instance reports."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-instance-type')
        client = APIClient()

        # kludge!  see test_get_costs_csv()
        client.credentials(HTTP_AUTHORIZATION=token, HTTP_ACCEPT='text/csv')

        response = client.get(url, content_type='text/csv')
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_storage_csv(self):
        """Test CSV output of inventory storage reports."""
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('reports-storage')
        client = APIClient()

        # kludge!  see test_get_costs_csv()
        client.credentials(HTTP_AUTHORIZATION=token, HTTP_ACCEPT='text/csv')

        response = client.get(url, content_type='text/csv')
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)
