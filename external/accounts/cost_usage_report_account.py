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
"""Cost Of Usage Report (CUR) object to be used by Masu Orchestrator/Processor to download CURs."""


class CostUsageReportAccount:
    """Object to hold attributes needed to download a CUR."""

    def __init__(self, authentication, billing_source, customer_name, provider_type):
        """Set account attributes."""
        self.authentication = authentication
        self.billing_source = billing_source
        self.customer_name = customer_name
        self.provider_type = provider_type

    def get_access_credential(self):
        """
        Return account authentication credential.

        Credential needed to access a CUR from a backing cloud service.

        Args:
            None

        Returns:
            (String) : Authentication attribute
                       example: For AWS - RoleARN

        """
        return self.authentication

    def get_billing_source(self):
        """
        Return the CUR source name.

        Identifier for where the CUR is located on the backing cloud service.

        Args:
            None

        Returns:
            (String) : Name of the source where the CUR is stored.
                       example: For AWS -S3 Bucket name

        """
        return self.billing_source

    def get_customer(self):
        """
        Return the name of the customer.

        Args:
            None

        Returns:
            (String) : Name of the customer associated with the account.
                       example: Test Customer

        """
        return self.customer_name

    def get_provider_type(self):
        """
        Return the provider type.

        Args:
            None

        Returns:
            (String) : Name of the provider that the account is associated with.
                       example: AWS

        """
        return self.provider_type
