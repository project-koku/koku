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


class ProviderAccessor:
    """Provider interface for koku to use."""

    def __init__(self, service_name):
        """Set the backend serve."""
        valid_services = Provider.PROVIDER_CHOICES[0]
        if service_name not in valid_services:
            LOG.error('{} is not a valid provider'.format(service_name))

        self.service = self._create_service(service_name)

    def _create_service(self, service_name):
        """
        Create the provider service object.

        This will establish what service (AWS, etc) ProviderAccessor should use
        when interacting with Koku core.

        Args:
            service_name (String): Provider Type

        Returns:
            (Object) : Some object that is a child of ProviderInterface

        """
        if service_name == 'AWS':
            return AWSProvider()

    def service_name(self):
        """
        Return the name of the provider service.

        This will establish what service (AWS, etc) ProviderAccessor should use
        when interacting with Koku core.

        Args:
            None

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        return self.service.name()

    def cost_usage_source_ready(self, credential, source_name):
        """
        Return the state of the cost usage source.

        Connectivity and account validation checks are performed to
        ensure that Koku can access a cost usage report from the provider.

        Args:
            credential (String): Provider Resource Name
                                 example: AWS - RoleARN
                                          arn:aws:iam::589175555555:role/CostManagement
            source_name (String): Identifier of the cost usage report source
                                  example: AWS - S3 Bucket

        Returns:
            None

        Raises:
            ValidationError: Error string

        """
        return self.service.cost_usage_source_is_reachable(credential, source_name)
