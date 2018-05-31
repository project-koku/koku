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
"""Provider external interface for koku to consume."""


import logging

from providers.aws.aws_provider import AWSProvider

from api.provider.models import Provider


LOG = logging.getLogger(__name__)


class ProviderAccess:
    """Provider interface for koku to use."""

    def __init__(self, service_name):
        """Set the backend serve."""
        valid_services = Provider.PROVIDER_CHOICES[0]
        if service_name not in valid_services:
            LOG.error('{} is not a valid provider'.format(service_name))

        self.service = self._create_service(service_name)

    def _create_service(self, service_name):
        """Create the service object."""
        if service_name == 'AWS':
            return AWSProvider()

    def service_name(self):
        """Return service name."""
        return self.service.name()

    def cost_usage_source_ready(self, credential, source_name):
        """Return cost usage source status."""
        return self.service.cost_usage_source_is_reachable(credential, source_name)
