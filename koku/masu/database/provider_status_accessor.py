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
"""Provider status accessors."""
import enum
import logging

from api.provider.models import ProviderStatus
from masu.database.koku_database_access import KokuDBAccess
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.exceptions import MasuProviderError
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class ProviderStatusCode(enum.IntEnum):
    """Enum class of provider status.

    This mirrors the model states in koku.api.provider.models

    """

    NEW = 0
    READY = 1
    WARNING = 33
    DISABLED_ERROR = 98
    DISABLED_ADMIN = 99


class ProviderStatusAccessor(KokuDBAccess):
    """Utility class to manage provider status."""

    MAX_RETRIES = 10

    def __init__(self, provider_uuid, schema="public"):
        """
        Establish ProviderStatus database connection.

        Args:
            provider_uuid  (String) the uuid of the provider
            schema         (String) database schema (i.e. public or customer tenant value)

        """
        super().__init__(schema)
        self._provider_uuid = provider_uuid
        self._table = ProviderStatus

        with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
            if not provider:
                raise MasuProviderError(f"Unknown provider: {self._provider_uuid}")
            self.provider_uuid = provider.uuid

        self._obj = self._get_db_obj_query().order_by("-id").first()

        # default to READY if there is no previous status.
        if self._obj is None:
            message = (
                f"No status found for provider {provider_uuid} in " + f'schema "{schema}". Setting status to READY.'
            )
            LOG.debug(message)
            ready_status = {
                "provider_id": self.provider_uuid,
                "status": ProviderStatusCode.READY,
                "last_message": "none",
                "timestamp": DateAccessor().today(),
                "retries": 0,
            }
            self.add(**ready_status)
            self._obj = self._get_db_obj_query().first()

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the provider object.

        Args:
            None
        Returns:
            (django.db.query.QuerySet): QuerySet of objects matching the given filters

        """
        return super()._get_db_obj_query(provider_id=self.provider_uuid)

    def get_status(self):
        """
        Return the provider status.

        Args:
            None
        Returns:
            (int): Status code

        """
        return self._obj.status

    def get_provider_uuid(self):
        """
        Return the provider uuid.

        Args:
            None
        Returns:
            (uuid.uuid4): Provider uuid

        """
        return self._provider_uuid

    def get_last_message(self):
        """
        Return the provider last_message.

        Args:
            None
        Returns:
            (str): Error message, if any

        """
        return self._obj.last_message

    def get_timestamp(self):
        """
        Return the provider status timestamp.

        Args:
            None
        Returns:
            (datetime): Timestamp for the status

        """
        return self._obj.timestamp

    def get_retries(self):
        """
        Return the provider status retry count.

        Args:
            None
        Returns:
            (int): Status retry count

        """
        return self._obj.retries
