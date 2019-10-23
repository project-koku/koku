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
"""Provider status."""

import logging
import random
from datetime import timedelta
from pprint import pformat

from masu.database.provider_status_accessor import (ProviderStatusAccessor,
                                                    ProviderStatusCode)
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class ProviderStatus(ProviderStatusAccessor):
    """Provider Status."""

    def __repr__(self):
        """Unambiguous representation."""
        out = {'is_valid': self.is_valid(),
               'is_backing_off': self.is_backing_off()}
        for field in self._obj._meta.fields:
            out[field.name] = getattr(self._obj, field.name)
        return out

    def __str__(self):
        """String representation."""
        return pformat(self.__repr__())

    def is_backing_off(self):
        """Determine if the provider is waiting to retry."""
        def backoff(interval, maximum=64):
            """Exponential back-off."""
            return min(maximum, (2 ** (interval))) + (random.randint(0, 1000) / 1000.0)

        retries = self.get_retries()
        timestamp = self.get_timestamp()
        backoff_threshold = timestamp + timedelta(hours=backoff(retries,
                                                                maximum=24))

        LOG.debug('[%s] Provider: %s, Retries: %s, Timestamp: %s, Threshold: %s',
                  self.__class__, self.get_provider_uuid(), retries,
                  timestamp, backoff_threshold)

        if self.get_status() == ProviderStatusCode.WARNING and \
                retries <= ProviderStatusAccessor.MAX_RETRIES and \
                DateAccessor().today() <= backoff_threshold:
            return True
        return False

    def is_valid(self):
        """Determine if the provider is valid based on its previous status."""
        status = self.get_status()
        retries = self.get_retries()

        LOG.debug('[%s] Provider: %s, Status: %s Retries: %s',
                  self.__class__, self.get_provider_uuid(), status, retries)

        if status == ProviderStatusCode.READY:
            return True

        if status == ProviderStatusCode.WARNING and \
                retries <= ProviderStatusAccessor.MAX_RETRIES:
            return True

        return False

    def set_status(self, status, error=None):
        """Update the provider status.

        Args:
            status (int) Provider status code
            error (Exception) Exception raised during processing attempts

        Returns:
            None

        """
        LOG.debug('Updating provider status: Provider: %s, Status: %s, Error: %s',
                  self.get_provider_uuid(), status, error)

        self._obj.status = status
        self._obj.timestamp = DateAccessor().today()

        if status == ProviderStatusCode.READY:
            self._obj.retries = 0    # reset counter on success
        elif status == ProviderStatusCode.WARNING:
            self._obj.retries += 1

        if error is not None:
            self._obj.last_message = str(error)
        else:
            self._obj.last_message = 'none'
        self._obj.save()

    def set_error(self, error=None):
        """Update status to an error state.

        Args:
            error (Exception) Exception raised during processing attempts

        """
        # stay in warning state until max retries is exceeded
        if self.get_retries() >= ProviderStatusAccessor.MAX_RETRIES:
            self.set_status(ProviderStatusCode.DISABLED_ERROR, error)

        # stay in error state until Provider is fixed.
        # state will be reset by provider updates made via Koku API
        if self.get_status() not in [ProviderStatusCode.DISABLED_ERROR,
                                     ProviderStatusCode.DISABLED_ADMIN]:
            self.set_status(ProviderStatusCode.WARNING, error)
