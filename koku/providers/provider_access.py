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
from providers.aws_local.aws_local_provider import AWSLocalProvider
from providers.azure.azure_provider import AzureProvider
from providers.ocp.ocp_provider import OCPProvider
from providers.ocp_local.ocp_local_provider import OCPLocalProvider

from api.provider.models import Provider


LOG = logging.getLogger(__name__)


class ProviderAccessorError(Exception):
    """General Exception class for ProviderAccessor errors."""

    def __init__(self, message):
        """Set custom error message for ProviderAccessor errors."""
        self.message = message


class ProviderAccessor:
    """Provider interface for koku to use."""

    def __init__(self, service_name):
        """Set the backend serve."""
        valid_services = Provider.PROVIDER_CHOICES
        if not [service for service in valid_services if service_name in service]:
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
        elif service_name == 'AWS-local':
            return AWSLocalProvider()
        elif service_name == 'AZURE':
            return AzureProvider()
        elif service_name == 'OCP-local':
            return OCPLocalProvider()
        elif service_name == 'OCP':
            return OCPProvider()

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

    def infrastructure_type(self, provider_uuid, schema_name):
        """
        Return the name of the infrastructure that the provider is running on.

        Args:
            provider_uuid (String): Provider UUID
            schema_name (String): Database schema name

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        try:
            infrastructure_type = self.service.infra_type_implementation(provider_uuid, schema_name)
        except Exception as error:
            raise ProviderAccessorError(str(error))

        return infrastructure_type if infrastructure_type else 'Unknown'

    def infrastructure_key_list(self, infrastructure_type, schema_name):
        """
        Return a list of keys identifying the provider running on specified infrastructure type.

        Args:
            infrastructure_type (String): Provider type
            schema_name (String): Database schema name

        Returns:
            (List) : List of strings
                       example: ['ocp-cluster-on-aws-1', 'ocp-cluster-on-aws-2']

        """
        keys = []
        try:
            keys = self.service.infra_key_list_implementation(infrastructure_type, schema_name)
        except Exception as error:
            raise ProviderAccessorError(str(error))

        return keys
