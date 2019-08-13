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
"""Test the AWS notifiation (SNS) handler."""

import boto3
from unittest.mock import patch, Mock
import json
from masu.external.notifications.aws.aws_notification_handler import (
    AWSNotificationHandler,
    AWSNotificationHandlerError,
)
from masu.external.notifications.notification_interface import (
    NotificationInterfaceFilter,
)
import masu.test.external.notifications.helpers.sns_helpers as sns_helper

from masu.test import MasuTestCase


class AWSNotificationHandlerTest(MasuTestCase):
    """Test Cases for AWSNotificationHandler."""

    def setUp(self):
        super().setUp()
        self.confirm_headers = list(sns_helper.sns_subscription_confirm_headers)
        self.confirm_body_dict = dict(sns_helper.sns_subscription_confirm_body_dict)
        self.notification_headers = list(sns_helper.sns_notification_headers)
        self.notification_body_dict = dict(sns_helper.sns_notification_body_dict)

    @patch('masu.external.notifications.aws.aws_notification_handler.boto3.client')
    def test_confirm_subscription(self, mock_boto3_client):
        sns_client = Mock()
        sns_client.confirm_subscription.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 201}
        }
        mock_boto3_client.return_value = sns_client

        topic_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopic'
        body_dict = self.confirm_body_dict
        headers = sns_helper.modify_header_list(
            self.confirm_headers, 'X-Amz-Sns-Topic-Arn', topic_arn
        )
        body_dict['TopicArn'] = topic_arn
        body = json.dumps(body_dict)
        try:
            AWSNotificationHandler(headers, body, validation=False)
        except Exception:
            self.fail('Unexpected exception')

    @patch('masu.external.notifications.aws.aws_notification_handler.boto3.client')
    def test_confirm_subscription_not_successful(self, mock_boto3_client):
        sns_client = Mock()
        sns_client.confirm_subscription.return_value = {}
        mock_boto3_client.return_value = sns_client

        # Make the TopicArn into a non-standard, unexpected format
        topic_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopic'
        corrupted_arn_name = 'Mangle{}'.format(topic_arn)

        body_dict = self.confirm_body_dict

        headers = sns_helper.modify_header_list(
            self.confirm_headers, 'X-Amz-Sns-Topic-Arn', corrupted_arn_name
        )
        body_dict['TopicArn'] = corrupted_arn_name

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError):
            AWSNotificationHandler(headers, body, validation=False)

    def test_get_billing_source_non_top_level_manifest(self):
        headers = self.notification_headers
        body_dict = self.notification_body_dict

        # Set a non-top level manifest file.  It is non-top level because the file name is in a uuid named directory
        new_path = '/cur/20180701-20180801/58d25dAA-bcb7-4d6C-87CB-6d1f719428EF/cur-Manifest.json'
        new_message = body_dict['Message'].replace(
            '/koku/20180701-20180801/koku-Manifest.json', new_path
        )
        body_dict['Message'] = new_message

        body = json.dumps(body_dict)
        handler = AWSNotificationHandler(headers, body)
        with self.assertRaises(NotificationInterfaceFilter):
            handler.get_billing_source()

    def test_get_billing_source_top_level_manifest(self):
        headers = self.notification_headers
        body_dict = self.notification_body_dict

        body = json.dumps(body_dict)
        handler = AWSNotificationHandler(headers, body)
        s3_bucket = handler.get_billing_source()
        self.assertEqual(s3_bucket, 'cost-usage-bucket')

    def test_get_billing_source_non_manifest_file(self):
        headers = self.notification_headers

        body_dict = self.notification_body_dict

        # Set a non-manifest file (doesn't end in Manifest.json) in the notification body
        new_path = (
            '/koku/20180701-20180801/bb976103-7c20-4053-852c-ad0c4b778dd0/koku-1.csv.gz'
        )
        new_message = body_dict['Message'].replace(
            '/koku/20180701-20180801/koku-Manifest.json', new_path
        )
        body_dict['Message'] = new_message

        body = json.dumps(body_dict)
        handler = AWSNotificationHandler(headers, body)
        with self.assertRaises(NotificationInterfaceFilter):
            handler.get_billing_source()

    def test_get_billing_source_empty_body(self):
        headers = [('X-Amz-Sns-Message-Type', 'Notification')]
        body = u''
        handler = AWSNotificationHandler(headers, body)
        s3_bucket_name = handler.get_billing_source()
        self.assertEqual(s3_bucket_name, None)

    def test_get_billing_source_wrong_message_type(self):
        # Set the Message-Type to an unexpected value
        headers = [('X-Amz-Sns-Message-Type', 'RandomType')]
        body = u''
        with self.assertRaises(AWSNotificationHandlerError):
            AWSNotificationHandler(headers, body)

    def test_get_billing_source_unexpected_message_format(self):
        headers = self.notification_headers

        body_dict = self.notification_body_dict
        extra_message = '[{\"extra\": \"message\"}, '

        # Add an extra message in the body 'Message' list (we are currently assuming theres only 1)
        new_message = body_dict['Message'].replace('[', extra_message)
        body_dict['Message'] = new_message

        body = json.dumps(body_dict)

        handler = AWSNotificationHandler(headers, body)
        with self.assertRaises(AWSNotificationHandlerError):
            handler = AWSNotificationHandler(headers, body, validation=False)
            handler.get_billing_source()

    def test_missing_message_type(self):
        # Remove the Message-Type header from a notification header request.
        headers = sns_helper.modify_header_list(
            self.confirm_headers, 'X-Amz-Sns-Message-Type', None
        )
        body_dict = self.confirm_body_dict

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError):
            AWSNotificationHandler(headers, body, validation=False)

    def test_get_region_invalid_arn(self):
        # Removed a ':' in Topic ARN
        headers = sns_helper.modify_header_list(
            self.confirm_headers,
            'X-Amz-Sns-Topic-Arn',
            'arnaws:sns:us-east-1:123456789012:MyTopic',
        )
        body_dict = self.confirm_body_dict
        body_dict['TopicArn'] = 'arnaws:sns:us-east-1:123456789012:MyTopic'

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError) as error:
            AWSNotificationHandler(headers, body, validation=False)
        self.assertTrue('Unexpected region name' in str(error.exception))

    def test_get_region_invalid_arn_2(self):
        # Removed all ':' in Subscription ARN
        headers = sns_helper.modify_header_list(
            self.confirm_headers,
            'X-Amz-Sns-Topic-Arn',
            'arnawssnsus-east-1123456789012MyTopic',
        )
        body_dict = self.confirm_body_dict
        body_dict['TopicArn'] = 'arnawssnsus-east-1123456789012MyTopic'

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError) as error:
            AWSNotificationHandler(headers, body, validation=False)
        self.assertTrue('Unexpected Subscription ARN format' in str(error.exception))

    def test_get_region_unknown_region(self):
        # Set the region to an unknown value (mars-east-1) in the Topic-Arn
        headers = sns_helper.modify_header_list(
            self.confirm_headers,
            'X-Amz-Sns-Topic-Arn',
            'arn:aws:sns:mars-east-1:123456789012:MyTopic',
        )
        body_dict = self.confirm_body_dict
        body_dict['TopicArn'] = 'arn:aws:sns:mars-east-1:123456789012:MyTopic'

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError) as error:
            AWSNotificationHandler(headers, body, validation=False)
        self.assertTrue('Unexpected region name.' in str(error.exception))

    def test_get_region_missing_header(self):
        # Missing X-Amz-Sns-Topic-Arn
        headers = sns_helper.modify_header_list(
            self.confirm_headers, 'X-Amz-Sns-Topic-Arn', None
        )
        body_dict = self.confirm_body_dict

        body = json.dumps(body_dict)
        with self.assertRaises(AWSNotificationHandlerError) as error:
            AWSNotificationHandler(headers, body, validation=False)
        self.assertTrue('Missing Subscription ARN' in str(error.exception))
