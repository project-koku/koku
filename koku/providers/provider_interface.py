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
"""Provider interface to be used by Koku."""
from abc import ABC
from abc import abstractmethod


class ProviderInterface(ABC):
    """Koku interface definition to access backend provider services."""

    @abstractmethod
    def name(self):
        """
        Return the provider service's name.

        Implemented by provider specific class to return it's name.

        Args:
            None

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        pass

    @abstractmethod
    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """
        Verify that the cost usage report source is reachable by Koku.

        Implemented by provider specific class.  An account validation and
        connectivity check is to be done.

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
        pass

    @abstractmethod
    def infra_type_implementation(self, provider_uuid, schema_name):
        """
        Return the type of infrastructure the provider is running on.

        Args:
            None

        Returns:
            None

        Raises:
            ProviderAccessorError: Error string

        """
        pass

    @abstractmethod
    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """
        Return a list of key values to identify resources running on provided infrastructure type.

        Args:
            infrastructure_type (String): Provider type
            schema_name (String): Database schema name

        Returns:
            (List) : List of strings
                       example: ['ocp-cluster-on-aws-1', 'ocp-cluster-on-aws-2']

        Raises:
            ProviderAccessorError: Error string

        """
        pass
