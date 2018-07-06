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
"""Notification handler interface to be used by Masu."""

from abc import ABC, abstractmethod


class NotificationInterfaceFilter(Exception):
    """AWS Notification Handler filter."""

    pass


# pylint: disable=too-few-public-methods
class NotificationInterface(ABC):
    """Masu interface definition to handle notification based report processing."""

    @abstractmethod
    def get_billing_source(self):
        """
        Return the billing source from a cost usage report notification.

        Implemented by a notification handler class.  Must return a string
        that uniquely identifies the report source.

        Example: AWS - S3 bucket name

        Args:
            None

        Returns:
            (String) Name of the billing source.

        """
        pass
