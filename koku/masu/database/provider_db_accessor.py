#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Accessor for Provider information from koku database."""
from django.db import transaction

from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from masu.database.koku_database_access import KokuDBAccess


class ProviderDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Data."""

    def __init__(self, provider_uuid=None, auth_id=None):
        """
        Establish Provider database connection.

        Args:
            provider_uuid  (String) the uuid of the provider
            auth_id        (String) provider authentication database id

        """
        super().__init__("public")
        self._uuid = provider_uuid
        self._auth_id = auth_id
        self._table = Provider
        self._provider = None

    @property
    def provider(self):
        """Return the provider this accessor is instantiated for."""
        if self._provider is None:
            self._provider = self._get_db_obj_query().first()
        return self._provider

    @property
    def infrastructure(self):
        """Return the infrastructure object for the provider."""
        if self.provider:
            return self.provider.infrastructure
        return None

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the provider object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."

        """
        query = self._table.objects.all()
        if self._auth_id:
            query = query.filter(authentication_id=self._auth_id)
        if self._uuid:
            query = query.filter(uuid=self._uuid)
        return query

    def get_provider(self):
        """Return the provider."""
        return self.provider

    def get_uuid(self):
        """
        Return the provider uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"

        """
        return str(self.provider.uuid) if self.provider else None

    def get_provider_name(self):
        """
        Return the provider name.

        Args:
            None
        Returns:
            (String): "Provider Name assigned by the customer",
                    example: "Test Provider"

        """
        return self.provider.name if self.provider else None

    def get_type(self):
        """
        Return the provider type.

        Args:
            None
        Returns:
            (String): "Provider type.  Cloud backend name",
                    example: "AWS"

        """
        return self.provider.type if self.provider else None

    def get_authentication(self):
        """
        Return the authentication name information.

        Args:
            None
        Returns:
            (String): "Provider Resource Name.  i.e. AWS: RoleARN",
                    example: "arn:aws:iam::111111111111:role/CostManagement"

        """
        return self.provider.authentication.provider_resource_name

    def get_billing_source(self):
        """
        Return the billing source usage report source name.

        Args:
            None
        Returns:
            (String): "Identifier for cost usage report.  i.e. AWS: S3 Bucket",
                    example: "my-s3-cur-bucket"

        """
        return self.provider.billing_source.bucket

    def get_setup_complete(self):
        """
        Return whether or not a report has been processed.

        Args:
            None
        Returns:
            (Boolean): "True if a report has been processed for the provider.",

        """
        return self.provider.setup_complete if self.provider else None

    def setup_complete(self):
        """
        Set setup_complete to True.

        Args:
            None
        Returns:
            None

        """
        self.provider.setup_complete = True
        self.provider.save()

    def get_customer_uuid(self):
        """
        Return the provider's customer uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"

        """
        return str(self.provider.customer.uuid)

    def get_customer_name(self):
        """
        Return the provider's customer name.

        Args:
            None
        Returns:
            (String): "Name of the customer",
                    example: "Customer 1 Inc."

        """
        return self.get_schema()

    def get_schema(self):
        """
        Return the schema for the customer.

        Args:
            None
        Returns:
            (String): "Name of the database schema",

        """
        return self.provider.customer.schema_name

    def get_infrastructure_type(self):
        """Retrun the infrastructure type for an OpenShift provider."""
        if self.infrastructure:
            return self.infrastructure.infrastructure_type
        return None

    def get_infrastructure_provider_uuid(self):
        """Return the UUID of the infrastructure provider an OpenShift cluster is installed on."""
        if self.infrastructure:
            infra_uuid = self.infrastructure.infrastructure_provider.uuid
            return str(infra_uuid) if infra_uuid else None
        return None

    @transaction.atomic()
    def set_infrastructure(self, infrastructure_provider_uuid, infrastructure_type):
        """Create an infrastructure mapping for an OpenShift provider.

        Args:
            infrastructure_type (str): The provider type this cluster is installed on.
                Ex. AWS, AZURE, GCP
            infrastructure_provider_uuid (str): The UUID of the provider this cluster
                is installed on.

        Returns:
            None

        """
        mapping, _ = ProviderInfrastructureMap.objects.get_or_create(
            infrastructure_provider_id=infrastructure_provider_uuid, infrastructure_type=infrastructure_type
        )

        self.provider.infrastructure = mapping
        self.provider.save()

    def get_associated_openshift_providers(self):
        """Return a list of OpenShift clusters associated with the cloud provider."""
        associated_openshift_providers = []

        mapping = ProviderInfrastructureMap.objects.filter(infrastructure_provider_id=self.provider.uuid).first()

        if mapping:
            associated_openshift_providers = Provider.objects.filter(infrastructure=mapping).all()

        return associated_openshift_providers
