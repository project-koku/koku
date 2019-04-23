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

import logging
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase
from django.utils.translation import ugettext as _
from faker import Faker
from providers.aws.aws_provider import (AWSProvider,
                                        _check_cost_report_access,
                                        _check_s3_access,
                                        _get_configured_sns_topics,
                                        _get_sts_access,
                                        error_obj)
from rest_framework.exceptions import ValidationError

FAKE = Faker()


def _mock_boto3_exception():
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name='', error_response={})


def _mock_boto3_kwargs_exception(**kwargs):
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name='', error_response={})


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
        expected_access_key = FAKE.md5()
        expected_secret_access_key = FAKE.md5()
        expected_session_token = FAKE.md5()

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
        credentials = _get_sts_access(iam_arn)
        sts_client.assume_role.assert_called()
        self.assertEquals(credentials.get('aws_access_key_id'),
                          expected_access_key)
        self.assertEquals(credentials.get('aws_secret_access_key'),
                          expected_secret_access_key)
        self.assertEquals(credentials.get('aws_session_token'),
                          expected_session_token)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_sts_access_fail(self, mock_boto3_client):
        """Test _get_sts_access fail."""
        logging.disable(logging.NOTSET)
        sts_client = Mock()
        sts_client.assume_role.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = sts_client
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        with self.assertLogs(level=logging.CRITICAL):
            credentials = _get_sts_access(iam_arn)
            self.assertIn('aws_access_key_id', credentials)
            self.assertIn('aws_secret_access_key', credentials)
            self.assertIn('aws_session_token', credentials)
            self.assertIsNone(credentials.get('aws_access_key_id'))
            self.assertIsNone(credentials.get('aws_secret_access_key'))
            self.assertIsNone(credentials.get('aws_session_token'))

    @patch('providers.aws.aws_provider.boto3.resource')
    def test_check_s3_access(self, mock_boto3_resource):
        """Test _check_s3_access success."""
        s3_resource = Mock()
        s3_resource.meta.client.head_bucket.return_value = True
        mock_boto3_resource.return_value = s3_resource
        s3_exists = _check_s3_access('bucket', {})
        self.assertTrue(s3_exists)

    @patch('providers.aws.aws_provider.boto3.resource')
    def test_check_s3_access_fail(self, mock_boto3_resource):
        """Test _check_s3_access fail."""
        s3_resource = Mock()
        s3_resource.meta.client.head_bucket.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_resource.return_value = s3_resource
        s3_exists = _check_s3_access('bucket', {})
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
        topics = _get_configured_sns_topics('bucket', {})
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_configured_sns_topics_empty(self, mock_boto3_client):
        """Test _get_configured_sns_topics no topic configuration."""
        expected_topics = []
        s3_client = Mock()
        notification_configuration = {}
        s3_client.get_bucket_notification_configuration.return_value = notification_configuration
        mock_boto3_client.return_value = s3_client
        topics = _get_configured_sns_topics('bucket', {})
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_get_configured_sns_topics_fail(self, mock_boto3_client):
        """Test _get_configured_sns_topics fail."""
        expected_topics = []
        s3_client = Mock()
        s3_client.get_bucket_notification_configuration.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = s3_client
        topics = _get_configured_sns_topics('bucket', {})
        self.assertEqual(topics, expected_topics)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_check_cost_report_access(self, mock_boto3_client):
        """Test _check_cost_report_access success."""
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {'ReportDefinitions': [
            {'ReportName': FAKE.word(),
             'TimeUnit': 'HOURLY',
             'Format': 'textORcsv',
             'Compression': 'GZIP',
             'AdditionalSchemaElements': ['RESOURCES'],
             'S3Bucket': FAKE.word(),
             'S3Prefix': FAKE.word(),
             'S3Region': 'us-east-1',
             'AdditionalArtifacts': [],
             'RefreshClosedReports': True,
             'ReportVersioning': 'CREATE_NEW_REPORT'}],
            'ResponseMetadata': {'RequestId': FAKE.uuid4(),
                                 'HTTPStatusCode': 200,
                                 'HTTPHeaders': {'x-amzn-requestid': FAKE.uuid4(),
                                                 'content-type': 'application/x-amz-json-1.1',
                                                 'content-length': '1234',
                                                 'date': FAKE.date_time()},
                                 'RetryAttempts': 0}}
        mock_boto3_client.return_value = s3_client
        try:
            _check_cost_report_access(FAKE.word(),
                                      {'aws_access_key_id': FAKE.md5(),
                                       'aws_secret_access_key': FAKE.md5(),
                                       'aws_session_token': FAKE.md5()})
        except Exception as exc:
            self.fail(exc)

    @patch('providers.aws.aws_provider.boto3.client')
    def test_check_cost_report_access_fail(self, mock_boto3_client):
        """Test _check_cost_report_access fail."""
        s3_client = Mock()
        s3_client.describe_report_definitions.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = s3_client
        with self.assertRaises(ValidationError):
            _check_cost_report_access(FAKE.word(),
                                      {'aws_access_key_id': FAKE.md5(),
                                       'aws_secret_access_key': FAKE.md5(),
                                       'aws_session_token': FAKE.md5()},
                                      bucket='wrongbucket')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=dict(aws_access_key_id=FAKE.md5(),
                             aws_secret_access_key=FAKE.md5(),
                             aws_session_token=FAKE.md5()))
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
           return_value=dict(aws_access_key_id=None,
                             aws_secret_access_key=None,
                             aws_session_token=None))
    def test_cost_usage_source_is_reachable_no_access(self,
                                                      mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=dict(aws_access_key_id=FAKE.md5(),
                             aws_secret_access_key=FAKE.md5(),
                             aws_session_token=FAKE.md5()))
    def test_cost_usage_source_is_reachable_no_bucket(self,
                                                      mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', None)

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=dict(aws_access_key_id=FAKE.md5(),
                             aws_secret_access_key=FAKE.md5(),
                             aws_session_token=FAKE.md5()))
    @patch('providers.aws.aws_provider._check_s3_access', return_value=False)
    def test_cost_usage_source_is_reachable_no_bucket_exists(self,
                                                             mock_get_sts_access,
                                                             mock_check_s3_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable('iam_arn', 'bucket_name')

    @patch('providers.aws.aws_provider._get_sts_access',
           return_value=dict(aws_access_key_id=FAKE.md5(),
                             aws_secret_access_key=FAKE.md5(),
                             aws_session_token=FAKE.md5()))
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

    @patch('providers.aws.aws_provider.boto3.client')
    def test_cur_has_resourceids(self, mock_boto3_client):
        """Test that a CUR with resource IDs succeeds."""
        bucket = FAKE.word()
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {'ReportDefinitions': [
            {'ReportName': FAKE.word(),
             'TimeUnit': 'HOURLY',
             'Format': 'textORcsv',
             'Compression': 'GZIP',
             'AdditionalSchemaElements': ['RESOURCES'],
             'S3Bucket': bucket,
             'S3Prefix': FAKE.word(),
             'S3Region': 'us-east-1',
             'AdditionalArtifacts': [],
             'RefreshClosedReports': True,
             'ReportVersioning': 'CREATE_NEW_REPORT'}],
            'ResponseMetadata': {'RequestId': FAKE.uuid4(),
                                 'HTTPStatusCode': 200,
                                 'HTTPHeaders': {'x-amzn-requestid': FAKE.uuid4(),
                                                 'content-type': 'application/x-amz-json-1.1',
                                                 'content-length': '1234',
                                                 'date': FAKE.date_time()},
                                 'RetryAttempts': 0}}
        mock_boto3_client.return_value = s3_client
        try:
            _check_cost_report_access(FAKE.word(),
                                      {'aws_access_key_id': FAKE.md5(),
                                       'aws_secret_access_key': FAKE.md5(),
                                       'aws_session_token': FAKE.md5()},
                                      bucket=bucket)
        except Exception as exc:
            self.fail(str(exc))

    @patch('providers.aws.aws_provider.boto3.client')
    def test_cur_without_resourceids(self, mock_boto3_client):
        """Test that a CUR without resource IDs raises ValidationError."""
        bucket = FAKE.word()
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {'ReportDefinitions': [
            {'ReportName': FAKE.word(),
             'TimeUnit': 'HOURLY',
             'Format': 'textORcsv',
             'Compression': 'GZIP',
             'AdditionalSchemaElements': [],
             'S3Bucket': bucket,
             'S3Prefix': FAKE.word(),
             'S3Region': 'us-east-1',
             'AdditionalArtifacts': [],
             'RefreshClosedReports': True,
             'ReportVersioning': 'CREATE_NEW_REPORT'}],
            'ResponseMetadata': {'RequestId': FAKE.uuid4(),
                                 'HTTPStatusCode': 200,
                                 'HTTPHeaders': {'x-amzn-requestid': FAKE.uuid4(),
                                                 'content-type': 'application/x-amz-json-1.1',
                                                 'content-length': '1234',
                                                 'date': FAKE.date_time()},
                                 'RetryAttempts': 0}}
        mock_boto3_client.return_value = s3_client
        with self.assertRaises(ValidationError):
            _check_cost_report_access(FAKE.word(),
                                      {'aws_access_key_id': FAKE.md5(),
                                       'aws_secret_access_key': FAKE.md5(),
                                       'aws_session_token': FAKE.md5()},
                                      bucket=bucket)
