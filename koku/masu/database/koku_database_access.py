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

from django.db import IntegrityError
from django.db import transaction
from django.db.transaction import get_connection, savepoint_commit, savepoint_rollback
from django.db.transaction import savepoint as django_savepoint
from tenant_schemas.utils import schema_context

LOG = logging.getLogger(__name__)


class KokuDBAccess:
    """Base Class to connect to the koku database.

    Subclass of Django Atomic class to make use of atomic transactions
    with a schema/tenant context.
    """

    _savepoints = []

    # pylint: disable=no-member
    def __init__(self, schema):
        """
        Establish database connection.

        Args:
            schema       (String) database schema (i.e. public or customer tenant value)

        """
        self.schema = schema

    def __enter__(self):
        """Enter context manager."""
        connection = get_connection()
        if connection.get_autocommit():
            connection.set_autocommit(False)
        KokuDBAccess._savepoints.append(transaction.savepoint())
        connection.set_schema(self.schema)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager close session."""
        connection = get_connection()
        with schema_context(self.schema):
            if KokuDBAccess._savepoints:
                if exception_type:
                    transaction.savepoint_rollback(KokuDBAccess._savepoints.pop())
                else:
                    transaction.savepoint_commit(KokuDBAccess._savepoints.pop())
            if not connection.in_atomic_block:
                transaction.commit()
                connection.set_autocommit(True)
        connection.set_schema_to_public()

    # pylint: disable=no-self-use
    def close_session(self):
        """Close the database session (DEPRECATED)."""
        # pylint: disable=unnecessary-pass
        pass

    # pylint: disable=no-self-use
    def get_base(self):
        """Return the base classes (DEPRECATED)."""
        return None

    # pylint: disable=no-self-use
    def get_session(self):
        """Return Koku database connection session (DEPRECATED)."""
        return None

    # pylint: disable=no-self-use
    def get_engine(self):
        """Return Koku database connection engine (DEPRECATED)."""
        return None

    # pylint: disable=no-self-use
    def get_meta(self):
        """Return Koku database metadata connection (DEPRECATED)."""
        return None

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

    def commit(self):
        """
        Commit pending database changes.

        Args:
            None
        Returns:
            None

        """
        with schema_context(self.schema):
            transaction.commit()

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

    def savepoint(self, func, *args, **kwargs):
        """Wrap a db access function in a savepoint block.

        Args:
            func (bound method) a function reference.
            args (object) function's positional arguments
            kwargs (object) function's keyword arguments
        Returns:
            None

        """
        with schema_context(self.schema):
            try:
                sid = django_savepoint()
                func(*args, **kwargs)
                savepoint_commit(sid)

            except IntegrityError as exc:
                LOG.warning('query transaction failed: %s', exc)
                savepoint_rollback(sid)
