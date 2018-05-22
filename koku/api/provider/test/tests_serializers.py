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
"""Test the Provider serializers."""
import uuid
from unittest.mock import Mock

from rest_framework import serializers

from api.iam.serializers import CustomerSerializer, UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.serializers import ProviderSerializer


class ProviderSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def test_create_provider_fails_user(self):
        """Test creating a provider fails with no user."""
        provider = {'name': 'test_provider',
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        serializer = ProviderSerializer(data=provider)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider_fails_group(self):  # pylint: disable=C0103
        """Test creating a provider where group is not found for user."""
        provider = {'name': 'test_provider',
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        request = Mock()
        new_user = None
        serializer = UserSerializer(data=self.gen_user_data())
        if serializer.is_valid(raise_exception=True):
            new_user = serializer.save()
        request.user = new_user
        context = {'request': request}
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider_fails_customer(self):  # pylint: disable=C0103
        """Test creating a provider where customer is not found for user."""
        provider = {'name': 'test_provider',
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        request = Mock()
        new_user = None
        serializer = UserSerializer(data=self.gen_user_data())
        if serializer.is_valid(raise_exception=True):
            new_user = serializer.save()
        request.user = new_user
        context = {'request': request}
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider(self):
        """Test creating a provider."""
        provider = {'name': 'test_provider',
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        new_cust = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            new_cust = serializer.save()
        request = Mock()
        request.user = new_cust.owner
        context = {'request': request}
        instance = None
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()

        self.assertIsInstance(instance.uuid, uuid.UUID)
