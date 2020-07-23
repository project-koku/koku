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
"""Sources Patch Handler."""
import logging

from django.db import connections
from django.db import DEFAULT_DB_ALIAS

from sources import storage

LOG = logging.getLogger(__name__)


class SourcesPatchHandler:
    """Source update handler for PATCH requests."""

    def update_billing_source(self, source_id, billing_source):
        """Store billing source update."""
        connections[DEFAULT_DB_ALIAS].connection = None
        instance = storage.get_source(source_id, "Unable to PATCH", LOG.error)
        instance.billing_source = billing_source
        if instance.source_uuid:
            instance.pending_update = True

        instance.save()
        return True

    def update_authentication(self, source_id, authentication):
        """Store authentication update."""
        connections[DEFAULT_DB_ALIAS].connection = None
        instance = storage.get_source(source_id, "Unable to PATCH", LOG.error)
        instance.authentication = authentication
        if instance.source_uuid:
            instance.pending_update = True

        instance.save()
        return True
