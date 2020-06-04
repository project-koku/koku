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
"""Collector to get all Providers from koku database."""
from api.models import Provider
from masu.database.koku_database_access import KokuDBAccess


class ProviderCollector(KokuDBAccess):
    """Class to interact with the koku database for Provider Data."""

    def __init__(self, schema="public"):
        """
        Establish ProviderQuerier database connection.

        Args:
            schema         (String) database schema (i.e. public or customer tenant value)

        """
        super().__init__(schema)
        self._table = Provider

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the provider object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."

        """
        objs = (
            self._table.objects.select_related("authentication")
            .select_related("billing_source")
            .select_related("customer")
            .all()
        )
        return objs

    def get_providers(self):
        """
        Return all providers.

        Args:
            None
        Returns:
            ([sqlalchemy.ext.automap.api_provider]): ["Provider1", "Provider2"]

        """
        return self._get_db_obj_query()

    def get_provider_uuid_map(self):
        """
        Return all providers.
        Args:
            None.
        Returns:
            (dict): {provider.uuid1: provider1, provider.uuid2: provider2}
        """
        return {str(provider.uuid): provider for provider in self._get_db_obj_query()}
