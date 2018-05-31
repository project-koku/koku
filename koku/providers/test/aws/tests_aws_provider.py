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
"""Tests the AWSProvider implementation for the Koku interface."""

from unittest.mock import Mock, patch

import boto3
from botocore.auth import SigV4Auth
from botocore.exceptions import NoCredentialsError
from django.test import TestCase
from moto import mock_s3, mock_sts
from providers.aws.aws_provider import AWSProvider, _get_sts_access
from rest_framework.exceptions import ValidationError


class AWSProviderTestCase(TestCase):
    """Parent Class for AWSProvider test cases."""

    def setup(self):
        """Create test case objects."""
        pass

    def tearDown(self):
        """Tear down test case objects."""
        pass

    def test_get_name(self):
        """Get name of provider."""
        provider = AWSProvider()
        self.assertEqual(provider.name(), 'AWS')

    @mock_sts
    @mock_s3
    @patch('providers.aws.aws_provider._check_org_access')
    def test_cost_usage_source_is_reachable(self, check_org_access):
        """Verify that the cost usage source is authenticated and created."""
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

        provider_interface = AWSProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)
        except Exception:
            self.fail('Unexpected Error')

    @patch('providers.aws.aws_provider._get_sts_access')
    def test_provider_sts_fail(self, get_sts_access):
        """Test creating a provider with AWS STS failure."""
        get_sts_access.return_value = (None, None, None)
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'

        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)

    @mock_sts
    @patch('providers.aws.aws_provider._check_s3_access')
    def test_provider_s3_fail(self, check_s3_access):
        """Test creating a provider with AWS s3 bucket doesn't exist."""
        check_s3_access.return_value = False
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'

        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)

    @mock_sts
    @mock_s3
    @patch('providers.aws.aws_provider._check_org_access')
    def test_provider_org_fail(self, check_org_access):
        """Test creating a provider with AWS org access failure."""
        check_org_access.return_value = False
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'

        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)

        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        s3_resource = boto3.resource(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
        )
        s3_resource.create_bucket(Bucket=bucket_name)

        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)

    def test_no_credential_error(self):
        """Test attempting STS access where no credentials are found."""
        with patch.object(SigV4Auth, 'add_auth', side_effect=NoCredentialsError):
            iam_arn = 'arn:aws:s3:::my_s3_bucket'
            bucket_name = 'my_s3_bucket'

            provider_interface = AWSProvider()
            with self.assertRaises(ValidationError):
                provider_interface.cost_usage_source_is_reachable(iam_arn, bucket_name)

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
