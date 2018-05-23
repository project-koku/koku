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
"""Test the Provider views."""
from unittest.mock import patch

import boto3
from django.urls import reverse
from moto import mock_s3, mock_sts
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.serializers import _get_sts_access


class ProviderViewTest(IamTestCase):
    """Tests the provider view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        for customer in self.customer_data:
            response = self.create_customer(customer)
            self.assertEqual(response.status_code, 201)

    @mock_sts
    @mock_s3
    @patch('api.provider.view.serializers._check_org_access')
    def test_create_provider(self, check_org_access):
        """Test create a provider."""
        check_org_access.return_value = True
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        s3_resource = boto3.resource(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
        )
        s3_resource.create_bucket(Bucket=bucket_name)
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': iam_arn
                    },
                    'billing_source': {
                        'bucket': bucket_name
                    }}
        token = self.get_customer_owner_token(self.customer_data[0])
        url = reverse('provider-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.post(url, data=provider, format='json')
        self.assertEqual(response.status_code, 201)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.customer_data[0].get('owner').get('username'))
        check_org_access.assert_called_once()

    def test_create_provider_anon(self):
        """Test create a provider with an anonymous user."""
        url = reverse('provider-list')
        client = APIClient()
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        response = client.post(url, data=provider, format='json')
        self.assertEqual(response.status_code, 401)
