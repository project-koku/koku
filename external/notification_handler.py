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
"""Cost Usage Report notification handler."""

from masu.external import AWS_SNS_HEADER_MSG_TYPE
from masu.external.notifications.aws.aws_notification_handler import AWSNotificationHandler
from masu.external.notifications.notification_interface import NotificationInterfaceFilter


class NotificationHandlerError(Exception):
    """Notification Handler error."""

    pass


class NotificationHandlerFilter(Exception):
    """Notification Handler filter."""

    pass


# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
class NotificationHandler:
    """Interface for masu to handle report download/process notifications."""

    def __init__(self, header, body):
        """
        Set the handler based on the backend cloud provider.

        Args:
            header          ([(,)])  List of header key/value pair sets
            body            (String) String representation of the request body JSON

        Raises:
            (NotificationHandlerError): Object fails to be initialized.

        """
        self._headers = header
        self._body = body
        try:
            self._handler = self._set_handler()
        except Exception as err:
            raise NotificationHandlerError(str(err))

        if not self._handler:
            raise NotificationHandlerError('Unsupported cloud provider.')

    def _set_handler(self):
        """
        Create the notification handler object.

        Handler is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Some object that is a child of NotificationHandlerInterface (coming soon)

        """
        # Quick check to make sure we know what cloud the message is coming from.
        if self._search_header_for_string(AWS_SNS_HEADER_MSG_TYPE):
            return AWSNotificationHandler(self._headers, self._body)
        return None

    def _search_header_for_string(self, value):
        """
        Search the headers for a particular string.

        Method is general purpose and could belong in it's own utils file but for now
        it's a quick way to verify that the message is coming from a source that we expect.

        Args:
            None

        Returns:
            (Boolean) : True if string is found in header, else False

        """
        for header in self._headers:
            if header[0] == value:
                return True
        return False

    def billing_source(self):
        """
        Retrieve the notified billing source for the notification.

        Args:
            None

        Returns:
            (String) Name of the billing source from the notification
                     example: AWS - S3 bucket name
        Raises:
            (NotificationHandlerFilter): Is raised when a notification handler
                                         filters a notification handling request.

        """
        try:
            source_name = self._handler.get_billing_source()
        except NotificationInterfaceFilter as info:
            raise NotificationHandlerFilter(str(info))
        except Exception as error:
            raise NotificationHandlerError(str(error))

        return source_name
