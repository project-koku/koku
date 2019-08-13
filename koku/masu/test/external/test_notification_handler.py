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

"""Test the NotificationHandler object."""

from unittest.mock import patch
import json
from masu.external.notification_handler import (
    NotificationHandler,
    NotificationHandlerError,
)
import masu.test.external.notifications.helpers.sns_helpers as sns_helper
from masu.test import MasuTestCase


class NotificationHandlerTest(MasuTestCase):
    """Test Cases for the NotificationHandler object."""

    def setUp(self):
        super().setUp()
        self.notification_headers = list(sns_helper.sns_notification_headers)
        self.notification_body_dict = dict(sns_helper.sns_notification_body_dict)

    def test_initializer(self):
        """Test to initializer success."""
        headers = self.notification_headers
        body_dict = self.notification_body_dict
        body = json.dumps(body_dict)

        handler = NotificationHandler(headers, body)
        self.assertIsNotNone(handler._handler)

    def test_initializer_error_setting_handler(self):
        """Test to initializer error setting handler."""
        # Use invalid type
        invalid_msg_type = 'InvalidType'
        headers = sns_helper.modify_header_list(
            self.notification_headers, 'X-Amz-Sns-Message-Type', invalid_msg_type
        )
        body_dict = self.notification_body_dict
        body_dict['Type'] = invalid_msg_type

        body = json.dumps(body_dict)

        with self.assertRaises(NotificationHandlerError) as error:
            NotificationHandler(headers, body)
        self.assertTrue('Unexpected message type' in str(error.exception))

    def test_initializer_unsupported_provider(self):
        """Test to initializer unknown provider."""
        headers = [
            ('X-Wizz-Bang-Message-Type', 'Notification'),
            ('Content-Length', 761),
            ('Content-Type', 'text/plain; charset=UTF-8'),
            ('Connection', 'Keep-Alive'),
            ('User-Agent', 'Amazon Simple Notification Service Agent'),
        ]

        body_dict = {
            'Type': 'Notification',
            'MessageId': '869ace9b-691a-5148-a22c-9d2e1e46e3de',
            'Subject': 'Wizz Bang Notification',
            'Timestamp': '2018-07-03T13:07:40.924Z',
        }
        body = json.dumps(body_dict)

        with self.assertRaises(NotificationHandlerError) as error:
            NotificationHandler(headers, body)
        self.assertTrue('Unsupported cloud provider.' in str(error.exception))

    def test_billing_source_exception(self):
        """Test to initializer success."""
        headers = self.notification_headers
        extra_message = '[{\'extra\': \'message\'}, '
        body_dict = self.notification_body_dict

        # Add an extra message in the body 'Message' list (we are currently assuming theres only 1)
        new_message = body_dict['Message'].replace('[', extra_message)
        body_dict['Message'] = new_message

        body = json.dumps(body_dict)

        handler = NotificationHandler(headers, body)
        with self.assertRaises(NotificationHandlerError):
            handler = NotificationHandler(headers, body)
            handler.billing_source()
