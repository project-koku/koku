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

from api.provider.models import Provider
from masu.database.customer_db_accessor import CustomerDBAccessor
from masu.database.koku_database_access import KokuDBAccess
from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from masu.database.provider_billing_source_db_accessor import ProviderBillingSourceDBAccessor


class ProviderDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Data."""

    def __init__(self, provider_uuid=None, auth_id=None):
        """
        Establish Provider database connection.

        Args:
            provider_uuid  (String) the uuid of the provider
            auth_id        (String) provider authentication database id

        """
        super().__init__('public')
        self._uuid = provider_uuid
        self._auth_id = auth_id
        self._table = Provider

    # pylint: disable=arguments-differ
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
        return self._get_db_obj_query().first()

    def get_uuid(self):
        """
        Return the provider uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"

        """
        obj = self._get_db_obj_query().first()
        return str(obj.uuid) if obj else None

    def get_provider_name(self):
        """
        Return the provider name.

        Args:
            None
        Returns:
            (String): "Provider Name assigned by the customer",
                    example: "Test Provider"

        """
        obj = self._get_db_obj_query().first()
        return obj.name if obj else None

    def get_type(self):
        """
        Return the provider type.

        Args:
            None
        Returns:
            (String): "Provider type.  Cloud backend name",
                    example: "AWS"

        """
        obj = self._get_db_obj_query().first()
        return obj.type if obj else None

    def get_authentication(self):
        """
        Return the authentication name information.

        Args:
            None
        Returns:
            (String): "Provider Resource Name.  i.e. AWS: RoleARN",
                    example: "arn:aws:iam::111111111111:role/CostManagement"

        """
        obj = self._get_db_obj_query().first()
        authentication_id = obj.authentication_id
        with ProviderAuthDBAccessor(authentication_id) as auth_accessor:
            provider_resource_name = auth_accessor.get_provider_resource_name()
        return provider_resource_name

    def get_billing_source(self):
        """
        Return the billing source usage report source name.

        Args:
            None
        Returns:
            (String): "Identifier for cost usage report.  i.e. AWS: S3 Bucket",
                    example: "my-s3-cur-bucket"

        """
        obj = self._get_db_obj_query().first()
        billing_source_id = obj.billing_source_id
        with ProviderBillingSourceDBAccessor(billing_source_id) as billing_accessor:
            bucket = billing_accessor.get_bucket()
        return bucket

    def get_setup_complete(self):
        """
        Return whether or not a report has been processed.

        Args:
            None
        Returns:
            (Boolean): "True if a report has been processed for the provider.",

        """
        obj = self._get_db_obj_query().first()
        return obj.setup_complete if obj else None

    def setup_complete(self):
        """
        Set setup_complete to True.

        Args:
            None
        Returns:
            None

        """
        obj = self._get_db_obj_query().first()
        obj.setup_complete = True
        obj.save()

    def get_customer_uuid(self):
        """
        Return the provider's customer uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"

        """
        obj = self._get_db_obj_query().first()
        customer_id = obj.customer_id
        with CustomerDBAccessor(customer_id) as customer_accessor:
            uuid = customer_accessor.get_uuid()
        return uuid

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
        obj = self._get_db_obj_query().first()
        customer_id = obj.customer_id
        with CustomerDBAccessor(customer_id) as customer_accessor:
            schema_name = customer_accessor.get_schema_name()
        return schema_name
