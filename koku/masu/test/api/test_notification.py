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

"""Test the notification endpoint view."""
import json
from unittest.mock import patch

from django.test import TestCase


class NotificationAPIViewTest(TestCase):
    """Test Cases for the notification API."""

    file_list = [
        '/var/tmp/masu/region/aws/catch-clearly.csv',
        '/var/tmp/masu/base/aws/professor-hour-industry-television.csv',
    ]

    @patch('masu.processor.orchestrator.Orchestrator.prepare', return_value=file_list)
    @patch(
        'masu.external.notifications.aws.aws_notification_handler.AWSNotificationHandler._confirm_subscription',
        returns=None,
    )
    def skip_test_notification_handle_notification(self, file_list, mock_confirm):
        """Test the notification handling endpoint with Notification msg."""
        topic_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopic'
        subscribe_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopicSubscribe'

        header = {
            'X-Amz-Sns-Message-Type': 'Notification',
            'X-Amz-Sns-Message-Id': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'Content-Length': '1867',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Host': 'masu.net:6868',
            'Connection': 'Keep-Alive',
            'User-Agent': 'Amazon Simple Notification Service Agent',
            'Accept-Encoding': 'gzip,deflate',
        }
        header['X-Amz-Sns-Topic-Arn'] = topic_arn
        header['X-Amz-Sns-Subscription-Arn'] = subscribe_arn
        message = {
            'Records': [
                {'awsRegion': 'us-east-1',
                 'eventName': 'ObjectCreated:Put',
                 'eventSource': 'aws:s3',
                 'eventTime': '2018-07-04T18:04:41.770Z',
                 'eventVersion': '2.0',
                 'requestParameters': {'sourceIPAddress': '10.88.30.162'},
                 'responseElements': {
                     'x-amz-id-2': 'UKqyjaYspHsPnfk2S57/AtAUMqd8VO1lfuVYNP70KPfDj4ElgpulHkBBoil2PYyEdpfnLWyoUdY=',
                     'x-amz-request-id': 'E7B755F7341A5745'
                 },
                 's3': {'bucket': {'arn': 'arn:aws:s3:::cost-usage-bucket',
                                   'name': 'cost-usage-bucket',
                                   'ownerIdentity': {'principalId': 'A2V75OLLZ1ABF7'}},
                        'configurationId': 'CostUsageNotification',
                        'object': {'eTag': '963195a6fa85a9b98a1f93a981a805fd',
                                   'key': '/koku/20180701-20180801/koku-Manifest.json',
                                   'sequencer': '005B3D0C39955A17E5',
                                   'size': 6518},
                        's3SchemaVersion': '1.0'},
                 'userIdentity': {'principalId': 'AWS:AIDAJLSI7DTYBUZAOKHVM'}}
            ]
        }

        body_dict = {
            'Type': 'Notification',
            'MessageId': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'TopicArn': topic_arn,
            'Subject': 'Amazon S3 Notification',
            'Message': json.dumps(message),
            'Timestamp': '2018-07-04T18:04:41.844Z',
            'SignatureVersion': '1',
            'Signature': ('J7rG3Jd9SR0So5kbkOHgfSJvOVckW5paIEc7MTTraVe1DxKzImpwHAabEAqj1dI9daPe8Sl'
                          'IEK92HocNjgIj9Ox3n/KE+aN871QSQ5ISG1P54uqnkaw+fwfjsFwVGnUsNQ50ntaM9JlsK6'
                          'VarwnBKdEjP/EAIS00R+bueJQ0Yws8Xhvyzmw0zASRminho5EpMNpucUAY4oKjgn3Bir7MU'
                          '4d/d31ZZedrdKb35XcKpIs1lZj/MPHOWRM2NDG+6AhSlEbZ94IIi9ycqoRgDn16hIBVLMbFR'
                          'SdbeRjQqYUxru3Inp5upRqOUTw0yNPLPbdUD/+qiUYs9A1Mc+VPZ/M0PA=='),
            'SigningCertURL': ('https://sns.us-east-1.amazonaws.com/SimpleNotificationService-eaea6'
                               '120e66ea12e88dcd8bcbddca752.pem'),
            'UnsubscribeURL': ('https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&Subscription'
                               'Arn=arn:aws:sns:us-east-1:589179999999:CostUsageReportUpdateTopic:7d5'
                               '49a1b-502f-47f7-9469-9ed18671e76a'),
        }
        body = json.dumps(body_dict)
        response = self.client.post('/api/v1/notification/', headers=header, data=body)
        body = response.json

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['Content-Type'], 'text/html; charset=utf-8')

    @patch(
        'masu.external.notifications.aws.aws_notification_handler.AWSNotificationHandler._confirm_subscription',
        returns=None,
    )
    def skip_test_notification_handle_notification_error(self, mock_confirm):
        """Test the notification endpoint with error event."""
        topic_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopic'
        subscribe_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopicSubscribe'

        # Force error with invalid message type
        header = {
            'X-Amz-Sns-Message-Type': 'InvalidMessage',
            'X-Amz-Sns-Message-Id': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'Content-Length': '1867',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Host': 'masu.net:6868',
            'Connection': 'Keep-Alive',
            'User-Agent': 'Amazon Simple Notification Service Agent',
            'Accept-Encoding': 'gzip,deflate',
        }
        header['X-Amz-Sns-Topic-Arn'] = topic_arn
        header['X-Amz-Sns-Subscription-Arn'] = subscribe_arn

        message = {
            'Records': [
                {'awsRegion': 'us-east-1',
                 'eventName': 'ObjectCreated:Put',
                 'eventSource': 'aws:s3',
                 'eventTime': '2018-07-04T18:04:41.770Z',
                 'eventVersion': '2.0',
                 'requestParameters': {'sourceIPAddress': '10.88.30.162'},
                 'responseElements': {
                     'x-amz-id-2': 'UKqyjaYspHsPnfk2S57/AtAUMqd8VO1lfuVYNP70KPfDj4ElgpulHkBBoil2PYyEdpfnLWyoUdY=',
                     'x-amz-request-id': 'E7B755F7341A5745'},
                 's3': {'bucket': {'arn': 'arn:aws:s3:::cost-usage-bucket',
                                   'name': 'cost-usage-bucket',
                                   'ownerIdentity': {'principalId': 'A2V75OLLZ1ABF7'}},
                        'configurationId': 'CostUsageNotification',
                        'object': {'eTag': '963195a6fa85a9b98a1f93a981a805fd',
                                   'key': '/koku/20180701-20180801/koku-Manifest.json',
                                   'sequencer': '005B3D0C39955A17E5',
                                   'size': 6518},
                        's3SchemaVersion': '1.0'},
                 'userIdentity': {'principalId': 'AWS:AIDAJLSI7DTYBUZAOKHVM'}}
            ]
        }

        body_dict = {
            'Type': 'InvalidMessage',
            'MessageId': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'TopicArn': topic_arn,
            'Subject': 'Amazon S3 Notification',
            'Message': json.dumps(message),
            'Timestamp': '2018-07-04T18:04:41.844Z',
            'SignatureVersion': '1',
            'Signature': ('J7rG3Jd9SR0So5kbkOHgfSJvOVckW5paIEc7MTTraVe1DxKzImpwHAabEAqj1dI9daPe8Sl'
                          'IEK92HocNjgIj9Ox3n/KE+aN871QSQ5ISG1P54uqnkaw+fwfjsFwVGnUsNQ50ntaM9JlsK6'
                          'VarwnBKdEjP/EAIS00R+bueJQ0Yws8Xhvyzmw0zASRminho5EpMNpucUAY4oKjgn3Bir7MU'
                          '4d/d31ZZedrdKb35XcKpIs1lZj/MPHOWRM2NDG+6AhSlEbZ94IIi9ycqoRgDn16hIBVLMbF'
                          'RSdbeRjQqYUxru3Inp5upRqOUTw0yNPLPbdUD/+qiUYs9A1Mc+VPZ/M0PA=='),
            'SigningCertURL': ('https://sns.us-east-1.amazonaws.com/SimpleNotificationService-eaea'
                               '6120e66ea12e88dcd8bcbddca752.pem'),
            'UnsubscribeURL': ('https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&Subscripti'
                               'onArn=arn:aws:sns:us-east-1:589179999999:CostUsageReportUpdateTopi'
                               'c:7d549a1b-502f-47f7-9469-9ed18671e76a'),
        }
        body = json.dumps(body_dict)
        response = self.client.post('/api/v1/notification/', headers=header, data=body)
        body = response.json

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['Content-Type'], 'text/html; charset=utf-8')

    @patch(
        'masu.external.notifications.aws.aws_notification_handler.AWSNotificationHandler._confirm_subscription',
        returns=None,
    )
    def skip_test_notification_handle_notification_filter(self, mock_confirm):
        """Test the notification endpoint with filter event."""
        topic_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopic'
        subscribe_arn = 'arn:aws:sns:us-east-1:123456789012:MyTopicSubscribe'

        header = {
            'X-Amz-Sns-Message-Type': 'Notification',
            'X-Amz-Sns-Message-Id': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'Content-Length': '1867',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Host': 'masu.net:6868',
            'Connection': 'Keep-Alive',
            'User-Agent': 'Amazon Simple Notification Service Agent',
            'Accept-Encoding': 'gzip,deflate',
        }
        header['X-Amz-Sns-Topic-Arn'] = topic_arn
        header['X-Amz-Sns-Subscription-Arn'] = subscribe_arn

        message = {
            'Records':
                [{'awsRegion': 'us-east-1',
                  'eventName': 'ObjectCreated:Put',
                  'eventSource': 'aws:s3',
                  'eventTime': '2018-07-04T18:04:41.770Z',
                  'eventVersion': '2.0',
                  'requestParameters': {'sourceIPAddress': '10.88.30.162'},
                  'responseElements': {
                      'x-amz-id-2': 'UKqyjaYspHsPnfk2S57/AtAUMqd8VO1lfuVYNP70KPfDj4ElgpulHkBBoil2PYyEdpfnLWyoUdY=',
                      'x-amz-request-id': 'E7B755F7341A5745'},
                  's3': {'bucket': {'arn': 'arn:aws:s3:::cost-usage-bucket',
                                    'name': 'cost-usage-bucket',
                                    'ownerIdentity': {'principalId': 'A2V75OLLZ1ABF7'}},
                         'configurationId': 'CostUsageNotification',
                         'object': {
                             'eTag': '963195a6fa85a9b98a1f93a981a805fd',
                             'key': '/koku/20180701-20180801/bb976103-7c20-4053-852c-ad0c4b778dd0/koku-Manifest.json',
                             'sequencer': '005B3D0C39955A17E5',
                             'size': 6518},
                         's3SchemaVersion': '1.0'},
                  'userIdentity': {'principalId': 'AWS:AIDAJLSI7DTYBUZAOKHVM'}}
                 ]
        }

        # Force filter with non-top level manifest file
        body_dict = {
            'Type': 'Notification',
            'MessageId': '156c18c0-c49f-5067-b3ab-4b77cae67e77',
            'TopicArn': topic_arn,
            'Subject': 'Amazon S3 Notification',
            'Message': json.dumps(message),
            'Timestamp': '2018-07-04T18:04:41.844Z',
            'SignatureVersion': '1',
            'Signature': ('J7rG3Jd9SR0So5kbkOHgfSJvOVckW5paIEc7MTTraVe1DxKzImpwHAabEAqj1dI9daPe8Sl'
                          'IEK92HocNjgIj9Ox3n/KE+aN871QSQ5ISG1P54uqnkaw+fwfjsFwVGnUsNQ50ntaM9JlsK6'
                          'VarwnBKdEjP/EAIS00R+bueJQ0Yws8Xhvyzmw0zASRminho5EpMNpucUAY4oKjgn3Bir7MU'
                          '4d/d31ZZedrdKb35XcKpIs1lZj/MPHOWRM2NDG+6AhSlEbZ94IIi9ycqoRgDn16hIBVLMbF'
                          'RSdbeRjQqYUxru3Inp5upRqOUTw0yNPLPbdUD/+qiUYs9A1Mc+VPZ/M0PA=='),
            'SigningCertURL': ('https://sns.us-east-1.amazonaws.com/SimpleNotificationService-eaea'
                               '6120e66ea12e88dcd8bcbddca752.pem'),
            'UnsubscribeURL': ('https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&Subscript'
                               'ionArn=arn:aws:sns:us-east-1:589179999999:CostUsageReportUpdateTo'
                               'pic:7d549a1b-502f-47f7-9469-9ed18671e76a'),
        }
        body = json.dumps(body_dict)
        response = self.client.post('/api/v1/notification/', headers=header, data=body)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['Content-Type'], 'text/html; charset=utf-8')
