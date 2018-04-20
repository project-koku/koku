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

"""Models to capture server information."""

import logging
import uuid

from django.db import models, transaction

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class ServerInformation(models.Model):
    """A server's information."""

    global_identifier = models.CharField(
        max_length=36,
        null=False
    )

    def __str__(self):
        """Convert to string."""
        return '{' +\
            'id:{}, global_identifier:{}'.format(self.id,
                                                 self.global_identifier) + '}'

    @staticmethod
    @transaction.atomic
    def create_or_retreive_server_id():
        """Create or retreive server's global identifier."""
        server_info = ServerInformation.objects.first()
        if server_info is None:
            server_info = ServerInformation(
                global_identifier=str(uuid.uuid4()))
            server_info.save()
            logger.info(
                'Server identification not found.  '
                'Initializing server identifier to %s.',
                server_info.global_identifier)
        return server_info.global_identifier
