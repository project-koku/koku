#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
