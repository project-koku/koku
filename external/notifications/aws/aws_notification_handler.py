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
"""AWS Notification Handler."""

import json
import logging
import re

import boto3

from masu.external import (AWS_REGIONS, AWS_SNS_HEADER_MSG_TYPE, AWS_SNS_HEADER_TOPIC_ARN)
from masu.external.notifications.notification_interface import (NotificationInterface,
                                                                NotificationInterfaceFilter)

LOG = logging.getLogger(__name__)


class AWSNotificationHandlerError(Exception):
    """AWS Notification Handler error."""

    pass


# pylint: disable=too-few-public-methods
class AWSNotificationHandler(NotificationInterface):
    """AWS SNS notification handler."""

    UUID_REGEX = '[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'

    def __init__(self, header, body, validation=True):
        """
        Initializer.

        Args:
            header          ([(,)])  List of header key/value pair sets
            body            (String) String representation of the request body JSON
            validation      (Boolean) Flag to skip message signature validation (optional)

        """
        self._headers = header
        self._body = body
        self._msg_type = self._get_message_type()
        if validation:
            self._validate_message()
        self._confirm_subscription()

    def _validate_message(self):
        """
        Validate incoming message.

        Verify that the message payload matches the provided signature.

        Args:
            None

        Returns:
            TBD

        """
        # Validate signature of request body.  Throw exception if verification fails
        pass

    def get_billing_source(self):
        """
        Retrieve the name of the S3 bucket from the SNS notification.

        FIXME: Diving through the response body to extract values such as
        object_key and s3_bucket_name could be improved upon.  A concerted effort
        to determine whether or not there will always be one item in "Records"
        should be done to know that this method will be reliable.

        FIXME: The filtering for only top-level manifest files was done as a quick
        way to limit the number of download/processing requests.  If we can find a
        better way to ensure we are only responding to one notification when multiple
        files have changed in the bucket then the filtering could be removed.

        Args:
            None

        Returns:
            (String) Name of the billing source from the notification

        Raises:
            (NotificationInterfaceFilter): Is raised when the notification is not for
                                           a top-level manifest file.
            (AWSNotificationHandlerError): Is raised when parsing the notification body
                                           message fails.

        """
        s3_bucket_name = None
        if self._msg_type == 'Notification' and self._body:
            body_dict = json.loads(self._body)
            message_dict = json.loads(body_dict['Message'])

            # There must be a more reliable way of getting bucket name..
            object_key = None
            s3_bucket_name = None
            try:
                object_key = message_dict['Records'][0]['s3']['object']['key']
                s3_bucket_name = message_dict['Records'][0]['s3']['bucket']['name']
            except KeyError:
                raise AWSNotificationHandlerError('Unexpected \"Message\" element in body.')

            if object_key.endswith('Manifest.json'):
                if re.findall(self.UUID_REGEX, object_key.lower()):
                    msg = 'Ignoring non-toplevel manifest file: {}'.format(object_key)
                    raise NotificationInterfaceFilter(msg)

            if not object_key.endswith('Manifest.json'):
                msg = 'Ignoring non-manifest file: {}'.format(object_key)
                raise NotificationInterfaceFilter(msg)

        return s3_bucket_name if s3_bucket_name else None

    def _get_message_type(self):
        """
        Retrieve the type of SNS message.

        Args:
            None

        Returns:
            (String) Message type
            example:
                Notification             - Cost Usage Report S3 bucket events
                SubscriptionConfirmation - When subscribing Masu to the SNS Topic as
                                           an HTTP endpoint
        Raises:
            (AWSNotificationHandlerError): Is raised when the notification contains a
                                           message type other than 'SubscriptionConfirmation'
                                           or 'Notification'

        """
        msg_type = None
        for header in self._headers:
            if header[0] == AWS_SNS_HEADER_MSG_TYPE:
                msg_type = header[1]
                break

        valid_msg_types = ['SubscriptionConfirmation', 'Notification']
        if msg_type not in valid_msg_types:
            exception_msg = 'Unexpected message type. Found {}. Valid msgs: {}'
            raise AWSNotificationHandlerError(exception_msg.format(msg_type, valid_msg_types))

        return msg_type

    def _get_region(self):
        """
        Retrieve the region for the S3 bucket from the header.

        Assuming that the standard AWS ARN format is found in the X-Amz-Sns-Topic-Arn header
        Standard ARN format: arn:partition:service:region:account-id:resource

        Args:
            None

        Returns:
            (String) AWS region String
            example:
                us-east-1
        Raises:
            (AWSNotificationHandlerError): Is raised when the ARN parsing is not successful.

        """
        topic_arn = None
        for header in self._headers:
            if header[0] == AWS_SNS_HEADER_TOPIC_ARN:
                topic_arn = header[1]
                break
        if topic_arn:
            arn_elements = topic_arn.split(':', 5)
        else:
            raise AWSNotificationHandlerError('Missing Subscription ARN header')

        region = None
        try:
            region = arn_elements[3]
        except IndexError:
            err_msg = 'Unexpected Subscription ARN format. Found: {}'.format(topic_arn)
            raise AWSNotificationHandlerError(err_msg)

        if region not in AWS_REGIONS:
            unkn_region_msg = 'Unexpected region name.  Found {}. Expected {}.'
            raise AWSNotificationHandlerError(unkn_region_msg.format(region, str(AWS_REGIONS)))
        return region

    def _confirm_subscription(self):
        """
        Format and send SNS topic subscription confirmation message.

        Args:
            None

        Returns:
            None

        Raises:
            (AWSNotificationHandlerError): Is raised when a SNS topic subscription
                                           confirmation response is not successful.

        """
        if self._msg_type == 'SubscriptionConfirmation':
            body_dict = json.loads(self._body)
            topic_arn = body_dict['TopicArn']
            client = boto3.client('sns', region_name=self._get_region())
            confirm_msg = 'Confirming subscription to TopicARN: {}'.format(topic_arn)
            LOG.info(confirm_msg)
            try:
                response = client.confirm_subscription(
                    TopicArn=body_dict['TopicArn'],
                    Token=body_dict['Token'])
                response_code = response['ResponseMetadata']['HTTPStatusCode']
                LOG.info('SNS Topic subscription successful. Response Code: %s', response_code)
            except Exception as err:
                err_msg = 'Failed to subscribe to SNS Topic. Error: {}'.format(str(err))
                LOG.error(err_msg)
                raise AWSNotificationHandlerError(err_msg)
