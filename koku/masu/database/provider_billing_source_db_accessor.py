#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Accessor for Provider Billing Source from koku database."""
from api.provider.models import ProviderBillingSource
from masu.database.koku_database_access import KokuDBAccess


class ProviderBillingSourceDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Billing Source Data."""

    def __init__(self, billing_source_id, schema_name="public"):
        """
        Establish Provider Billing Source database connection.

        Args:
            billing_source_id  (String) the billing source unique database id
            schema_name        (String) database schema (i.e. public or customer tenant value)

        """
        super().__init__(schema_name)
        self._billing_source_id = billing_source_id
        self._table = ProviderBillingSource

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the provider billing source object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."

        """
        query = self._table.objects.filter(id=self._billing_source_id)
        return query

    def get_uuid(self):
        """
        Return the billing source uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"

        """
        obj = self._get_db_obj_query().first()
        return str(obj.uuid) if obj else None

    def get_data_source(self):
        """
        Return the cost usage report source name.

        Args:
            None
        Returns:
            (dict): "Identifier for cost usage report.  i.e. AWS: S3 Bucket",
                    example: {"bucket": "my-s3-cur-bucket"}

        """
        obj = self._get_db_obj_query().first()
        data_source = obj.data_source if obj else None
        return data_source
