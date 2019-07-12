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

from django.db import IntegrityError, transaction
from tenant_schemas.utils import schema_context

LOG = logging.getLogger(__name__)


class KokuDBAccess:
    """Base Class to connect to the koku database."""

    # pylint: disable=no-member
    def __init__(self, schema):
        """
        Establish database connection.

        Args:
            schema       (String) database schema (i.e. public or customer tenant value)
        """
        self.schema = schema
        self._savepoint = None

    def __enter__(self):
        """Context manager entry."""
        self._savepoint = transaction.savepoint()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager close session."""
        with schema_context(self.schema):
            if exception_type:
                transaction.savepoint_rollback(self._savepoint)
            else:
                transaction.savepoint_commit(self._savepoint)

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

    def add(self, use_savepoint=True, **kwargs):
        """
        Add a new row to this table.

        Args:
            use_savepoint (bool) whether a transaction savepoint should be used
            kwargs (Dictionary): Fields containing table attributes.

        Returns:
            (Object): new model object

        """
        with schema_context(self.schema):
            new_entry = self._table.objects.create(**kwargs)
            if use_savepoint:
                self.savepoint(new_entry.save)
            else:
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

    def delete(self, obj=None, use_savepoint=True):
        """
        Delete our object from the database.

        Args:
            obj (object) model object to delete
            use_savepoint (bool) whether a transaction savepoint should be used
        Returns:
            None
        """
        if obj:
            deleteme = obj
        else:
            deleteme = self._obj
        with schema_context(self.schema):
            if use_savepoint:
                self.savepoint(deleteme.delete)
            else:
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
                savepoint = transaction.savepoint()
                func(*args, **kwargs)
                transaction.savepoint_commit(savepoint)

            except IntegrityError as exc:
                LOG.warning('query transaction failed: %s', exc)
                transaction.savepoint_rollback(savepoint)
