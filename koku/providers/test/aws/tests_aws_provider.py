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

from botocore.exceptions import ClientError
from django.test import TestCase
from django.utils.translation import ugettext as _
from providers.aws.aws_provider import (AWSProvider,
                                        _check_cost_report_access,
                                        _check_s3_access,
                                        _get_configured_sns_topics,
                                        _get_sts_access,
                                        error_obj)
from rest_framework.exceptions import ValidationError


def _mock_boto3_exception():
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name='', error_response={})


def _mock_boto3_kwargs_exception(**kwargs):
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name='', error_response={})


def _mock_get_sts_access(credential_name):
    """Return mock values for sts access."""
    return 'access_key_id', 'secret_access_key', 'session_token'


class AWSProviderTestCase(TestCase):
    """Parent Class for AWSProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = AWSProvider()
        self.assertEqual(provider.name(), 'AWS')

    def test_error_obj(self):
        """Test the error_obj method."""
        test_key = 'tkey'
        test_message = 'tmessage'
        expected = {
            test_key: [_(test_message)]
        }
        error = error_obj(test_key, test_message)
        self.assertEqual(error, expected)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_sts_access(self, mock_boto3_client):
        """Test _get_sts_access success."""
        expected_access_key = 'mock_access_key_id'
        expected_secret_access_key = 'mock_secret_access_key'
        expected_session_token = 'mock_session_token'
        assume_role = {
            'Credentials': {
                'AccessKeyId': expected_access_key,
                'SecretAccessKey': expected_secret_access_key,
                'SessionToken': expected_session_token
            }
        }
        sts_client = Mock()
        sts_client.assume_role.return_value = assume_role
        mock_boto3_client.return_value = sts_client

        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertEqual(access_key_id, expected_access_key)
        self.assertEqual(secret_access_key, expected_secret_access_key)
        self.assertEqual(session_token, expected_session_token)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_sts_access_none(self, mock_boto3_client):
        """Test _get_sts_access handles no credentials."""
        assume_role = {}
        sts_client = Mock()
        sts_client.assume_role.return_value = assume_role
        mock_boto3_client.return_value = sts_client

        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertIsNone(access_key_id)
        self.assertIsNone(secret_access_key)
        self.assertIsNone(session_token)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_sts_access_fail(self, mock_boto3_client):
        """Test _get_sts_access fail."""
        sts_client = Mock()
        sts_client.assume_role.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = sts_client
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        access_key_id, secret_access_key, session_token = _get_sts_access(
            iam_arn)
        self.assertIsNone(access_key_id)
        self.assertIsNone(secret_access_key)
        self.assertIsNone(session_token)

    @patch('providers.aws.aws_provider.boto3.resource')
    def test_check_s3_access(self, mock_boto3_resource):
        """Test _check_s3_access success."""
        s3_resource = Mock()
        s3_resource.meta.client.head_bucket.return_value = True
        mock_boto3_resource.return_value = s3_resource
        s3_exists = _check_s3_access('access_key_id', 'secret_access_key',
                                     'session_token', 'bucket')
        self.assertTrue(s3_exists)

    @patch('providers.aws.aws_provider.boto3.resource')
    def test_check_s3_access_fail(self, mock_boto3_resource):
        """Test _check_s3_access fail."""
        s3_resource = Mock()
        s3_resource.meta.client.head_bucket.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_resource.return_value = s3_resource
        s3_exists = _check_s3_access('access_key_id', 'secret_access_key',
                                     'session_token', 'bucket')
        self.assertFalse(s3_exists)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_configured_sns_topics(self, mock_boto3_client):
        """Test _get_configured_sns_topics success."""
        expected_topics = ['t1', 't2']
        s3_client = Mock()
        notification_configuration = {
            'TopicConfigurations': [{'TopicArn': 't1'},
                                    {'TopicArn': 't2'}]
        }
        s3_client.get_bucket_notification_configuration.return_value = notification_configuration
        mock_boto3_client.return_value = s3_client
        topics = _get_configured_sns_topics('access_key_id',
                                            'secret_access_key',
                                            'session_token',
                                            'bucket')
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_configured_sns_topics_empty(self, mock_boto3_client):
        """Test _get_configured_sns_topics no topic configuration."""
        expected_topics = []
        s3_client = Mock()
        notification_configuration = {}
        s3_client.get_bucket_notification_configuration.return_value = notification_configuration
        mock_boto3_client.return_value = s3_client
        topics = _get_configured_sns_topics('access_key_id',
                                            'secret_access_key',
                                            'session_token',
                                            'bucket')
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_configured_sns_topics_fail(self, mock_boto3_client):
        """Test _get_configured_sns_topics fail."""
        expected_topics = []
        s3_client = Mock()
        s3_client.get_bucket_notification_configuration.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = s3_client
        topics = _get_configured_sns_topics('access_key_id',
                                            'secret_access_key',
                                            'session_token',
                                            'bucket')
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_check_cost_report_access(self, mock_boto3_client):
        """Test _check_cost_report_access success."""
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = True
        mock_boto3_client.return_value = s3_client
        access_ok = _check_cost_report_access('access_key_id',
                                              'secret_access_key',
                                              'session_token')
        self.assertTrue(access_ok)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_check_cost_report_access_fail(self, mock_boto3_client):
        """Test _check_cost_report_access fail."""
        s3_client = Mock()
        s3_client.describe_report_definitions.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = s3_client
        access_ok = _check_cost_report_access('access_key_id',
                                              'secret_access_key',
                                              'session_token')
        self.assertFalse(access_ok)

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=('access_key_id',
                         'secret_access_key',
                         'session_token'))
    @patch('providers.aws.aws_provider._check_s3_access', return_value=True)
    @patch('providers.aws.aws_provider._check_cost_report_access', return_value=True)
    @patch('providers.aws.aws_provider._get_configured_sns_topics', return_value=['t1'])
    def test_cost_usage_source_is_reachable(self,
                                            mock_get_sts_access,
                                            mock_check_s3_access,
                                            mock_check_cost_report_access,
                                            mock_get_configured_sns_topics):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        try:
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')
        except Exception:
            self.fail('Unexpected Error')

    def test_cost_usage_source_is_reachable_no_arn(self):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(None, 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=(None,
                         None,
                         None))
    def test_cost_usage_source_is_reachable_no_access(self,
                                                      mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=('access_key_id',
                         'secret_access_key',
                         'session_token'))
    def test_cost_usage_source_is_reachable_no_bucket(self,
                                                      mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', None)

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=('access_key_id',
                         'secret_access_key',
                         'session_token'))
    @patch('providers.aws.aws_provider._check_s3_access', return_value=False)
    def test_cost_usage_source_is_reachable_no_bucket_exists(self,
                                                             mock_get_sts_access,
                                                             mock_check_s3_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=('access_key_id',
                         'secret_access_key',
                         'session_token'))
    @patch('providers.aws.aws_provider._check_s3_access', return_value=True)
    @patch('providers.aws.aws_provider._check_cost_report_access', return_value=False)
    def test_cost_usage_source_is_reachable_no_cur(self,
                                                   mock_get_sts_access,
                                                   mock_check_s3_access,
                                                   mock_check_cost_report_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=('access_key_id',
                         'secret_access_key',
                         'session_token'))
    @patch('providers.aws.aws_provider._check_s3_access', return_value=True)
    @patch('providers.aws.aws_provider._check_cost_report_access', return_value=True)
    @patch('providers.aws.aws_provider._get_configured_sns_topics', return_value=[])
    def test_cost_usage_source_is_reachable_no_topics(self,
                                                      mock_get_sts_access,
                                                      mock_check_s3_access,
                                                      mock_check_cost_report_access,
                                                      mock_get_configured_sns_topics):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        try:
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')
        except Exception:
            self.fail('Unexpected Error')
