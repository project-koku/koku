#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Accessor for Provider information from koku database."""
from django.db import transaction

from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor


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
        self.date_accessor = DateAccessor()

    @property
    def provider(self):
        """Return the provider this accessor is instantiated for."""
        query = self._get_db_obj_query()
        if self._provider is None and query:
            self._provider = query.first()
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
        if not self._auth_id and not self._uuid:
            return self._table.objects.none()
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

    def get_credentials(self):
        """
        Return the credential information.

        Args:
            None
        Returns:
            (dict): {"credentials": "Provider Resource Name.  i.e. AWS: RoleARN"},
                    example: {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}

        """
        return self.provider.authentication.credentials

    def get_data_source(self):
        """
        Return the data_source information.

        Args:
            None
        Returns:
            (dict): "Identifier for cost usage report.  i.e. AWS: S3 Bucket",
                    example: {"bucket": "my-s3-cur-bucket"}

        """
        return self.provider.billing_source.data_source

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

    def set_data_updated_timestamp(self):
        """Set the data updated timestamp to the current time."""
        if self.provider:
            self.provider.data_updated_timestamp = self.date_accessor.today_with_timezone("UTC")
            self.provider.save()
