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
from unittest.mock import Mock, patch

import boto3
from moto import mock_s3, mock_sts
from rest_framework import serializers

from api.iam.serializers import CustomerSerializer, UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.serializers import (ProviderSerializer,
                                      _check_org_access,
                                      _check_s3_access,
                                      _get_sts_access)


class ProviderSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def test_create_provider_fails_user(self):
        """Test creating a provider fails with no user."""
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
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
                    'type': Provider.PROVIDER_AWS,
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
                    'type': Provider.PROVIDER_AWS,
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

    @mock_sts
    @mock_s3
    @patch('api.provider.serializers._check_org_access')
    def test_create_provider(self, check_org_access):
        """Test creating a provider."""
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
        check_org_access.assert_called_once()

    @patch('api.provider.serializers._get_sts_access')
    def test_provider_sts_fail(self, get_sts_access):
        """Test creating a provider with AWS STS failure."""
        get_sts_access.return_value = (None, None, None)
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': iam_arn
                    },
                    'billing_source': {
                        'bucket': bucket_name
                    }}
        new_cust = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            new_cust = serializer.save()
        request = Mock()
        request.user = new_cust.owner
        context = {'request': request}
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()
                get_sts_access.assert_called_once(iam_arn)

    @mock_sts
    @patch('api.provider.serializers._check_s3_access')
    def test_provider_s3_fail(self, check_s3_access):
        """Test creating a provider with AWS s3 bucket doesn't exist."""
        check_s3_access.return_value = False
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': iam_arn
                    },
                    'billing_source': {
                        'bucket': bucket_name
                    }}
        new_cust = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            new_cust = serializer.save()
        request = Mock()
        request.user = new_cust.owner
        context = {'request': request}
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()
                check_s3_access.assert_called_once(iam_arn)

    @mock_sts
    @mock_s3
    @patch('api.provider.serializers._check_org_access')
    def test_provider_org_fail(self, check_org_access):
        """Test creating a provider with AWS org access failure."""
        check_org_access.return_value = False
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
        new_cust = None
        serializer = CustomerSerializer(data=self.customer_data[0])
        if serializer.is_valid(raise_exception=True):
            new_cust = serializer.save()
        request = Mock()
        request.user = new_cust.owner
        context = {'request': request}
        serializer = ProviderSerializer(data=provider, context=context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            check_org_access.assert_called_once()

    @patch('boto3.client')
    def test_get_sts_access_no_cred(self, mock_boto3):
        """Test _get_sts_access with no credentials."""
        client = Mock()
        client.assume_role.return_value = {}
        mock_boto3.return_value = client
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertIsNone(access_key_id)
        self.assertIsNone(secret_access_key)
        self.assertIsNone(session_token)

    def test_get_sts_access_fail(self):
        """Test _get_sts_access with boto exception."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertIsNone(access_key_id)
        self.assertIsNone(secret_access_key)
        self.assertIsNone(session_token)

    @mock_sts
    def test_check_s3_access_no_bucket(self):
        """Test _check_s3_access with boto exception."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        s3_exists = _check_s3_access(access_key_id, secret_access_key,
                                     session_token, bucket_name)
        self.assertFalse(s3_exists)

    @mock_sts
    def test_check_org_access_fail(self):
        """Test _check_org_access with boto exception."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        access_exists = _check_org_access(access_key_id, secret_access_key,
                                          session_token)
        self.assertFalse(access_exists)

    def test_get_sts_access_invalid_param(self):
        """Test _get_sts_access with invalid RoleARN parameter."""
        iam_arn = 'invalid'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertIsNone(access_key_id)
        self.assertIsNone(secret_access_key)
        self.assertIsNone(session_token)
