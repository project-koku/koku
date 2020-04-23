#
# Copyright 2020 Red Hat, Inc.
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
"""Sources Error Message."""
import logging

from rest_framework.serializers import ValidationError

# from providers.provider_errors import ProviderErrors

LOG = logging.getLogger(__name__)


class SourcesErrorMessage:
    """Sources Error Message for Sources API service."""

    def __init__(self, error):
        """Initialize the message generator."""
        self._error = error

    @property
    def error_msg(self):
        err_msg = None
        if isinstance(self._error, ValidationError):
            _, err_msg = self._extract_from_validation_error()
        else:
            err_msg = str(self._error)
        return err_msg

    def _extract_from_validation_error(self):
        """Extract key and message from ValidationError."""
        err_key = None
        err_msg = None
        if isinstance(self._error, ValidationError):
            err_dict = self._error.detail
            err_key = list(err_dict.keys()).pop()
            err_body = err_dict.get(err_key).pop()
            err_msg = err_body.encode().decode("UTF-8")
        return err_key, err_msg

    def display(self):
        """Generate user friendly message."""
        if isinstance(self._error, ValidationError):
            key, msg = self._extract_from_validation_error()
            LOG.info(f"Error Status key: {str(key)} msg: {str(msg)}")
        else:
            msg = str(self._error)
        return msg
