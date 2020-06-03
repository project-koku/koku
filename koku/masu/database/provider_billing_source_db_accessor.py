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
"""Accessor for Provider Billing Source from koku database."""
from api.provider.models import ProviderBillingSource
from masu.database.koku_database_access import KokuDBAccess


class ProviderBillingSourceDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Billing Source Data."""

    def __init__(self, billing_source_id, schema="public"):
        """
        Establish Provider Billing Source database connection.

        Args:
            billing_source_id  (String) the billing source unique database id
            schema             (String) database schema (i.e. public or customer tenant value)

        """
        super().__init__(schema)
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

    def get_bucket(self):
        """
        Return the cost usage report source name.

        Args:
            None
        Returns:
            (String): "Identifier for cost usage report.  i.e. AWS: S3 Bucket",
                    example: "my-s3-cur-bucket"

        """
        obj = self._get_db_obj_query().first()
        bucket = obj.bucket if obj else None
        return bucket
