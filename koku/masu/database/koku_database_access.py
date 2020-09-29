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
"""Accessor for Customer information from koku database."""
import logging

from django.db import transaction
from django_tenants.utils import schema_context


LOG = logging.getLogger(__name__)


class KokuDBAccess:
    """Base Class to connect to the koku database.

    Subclass of Django Atomic class to make use of atomic transactions
    with a schema/tenant context.
    """

    def __init__(self, schema):
        """
        Establish database connection.

        Args:
            schema       (String) database schema (i.e. public or customer tenant value)

        """
        self.schema = schema

    def __enter__(self):
        """Enter context manager."""
        connection = transaction.get_connection()
        connection.set_schema(self.schema)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager reset schema to public and exit."""
        connection = transaction.get_connection()
        connection.set_schema_to_public()

    def _get_db_obj_query(self, **filter_args):
        """
        Return the django queryset for this table .

        Args:
            None
        Returns:
            (django.db.query.QuerySet): QuerySet of objects matching the given filters

        """
        with schema_context(self.schema):
            queryset = self._table.objects.all()
            if filter_args:
                queryset = queryset.filter(**filter_args)
            return queryset

    def does_db_entry_exist(self):
        """
        Return status for the existence of an object in the database.

        Args:
            None
        Returns:
            (Boolean): "True/False",

        """
        with schema_context(self.schema):
            return self._get_db_obj_query().exists()

    def add(self, **kwargs):
        """
        Add a new row to this table.

        Args:
            kwargs (Dictionary): Fields containing table attributes.

        Returns:
            (Object): new model object

        """
        with schema_context(self.schema):
            new_entry = self._table.objects.create(**kwargs)
            new_entry.save()
            return new_entry

    def delete(self, obj=None):
        """
        Delete our object from the database.

        Args:
            obj (object) model object to delete
        Returns:
            None

        """
        if obj:
            deleteme = obj
        else:
            deleteme = self._obj
        with schema_context(self.schema):
            deleteme.delete()
