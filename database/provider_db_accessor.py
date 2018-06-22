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


from masu.database.auth_db_accessor import AuthDBAccessor
from masu.database.customer_db_accessor import CustomerDBAccessor
from masu.database.koku_database_access import KokuDBAccess
from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from masu.database.provider_billing_source_db_accessor import ProviderBillingSourceDBAccessor


class ProviderDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Data."""

    def __init__(self, provider_uuid, schema='public'):
        """
        Establish Provider database connection.

        Args:
            provider_uuid  (String) the uuid of the provider
            schema         (String) database schema (i.e. public or customer tenant value)
        """
        super().__init__(schema)
        self._uuid = provider_uuid
        self._provider = self.get_base().classes.api_provider

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the provider object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."
        """
        obj = self.get_session().query(self._provider).filter_by(uuid=self._uuid)
        return obj

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
        return obj.uuid

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
        return obj.name

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
        return obj.type

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
        auth_accessor = ProviderAuthDBAccessor(authentication_id)
        return auth_accessor.get_provider_resource_name()

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
        billing_accessor = ProviderBillingSourceDBAccessor(billing_source_id)
        return billing_accessor.get_bucket()

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
        customer_accessor = CustomerDBAccessor(customer_id)
        return customer_accessor.get_uuid()

    def get_customer_name(self):
        """
        Return the provider's customer name.

        Args:
            None
        Returns:
            (String): "Name of the customer",
                    example: "Customer 1 Inc."
        """
        obj = self._get_db_obj_query().first()
        customer_id = obj.customer_id
        customer_accessor = CustomerDBAccessor(customer_id)
        group_ptr_id = customer_accessor.get_group_ptr_id()
        auth_accessor = AuthDBAccessor(group_ptr_id)
        return auth_accessor.get_name()

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
        customer_accessor = CustomerDBAccessor(customer_id)
        schema_name = customer_accessor.get_schema_name()
        return schema_name
