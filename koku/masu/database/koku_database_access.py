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

import sqlalchemy
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import scoped_session, sessionmaker

from masu.database.engine import DB_ENGINE

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
        self._db = DB_ENGINE
        self._meta = self._create_metadata()
        self._session_factory = sessionmaker(bind=self._db)
        self._session_registry = scoped_session(self._session_factory)
        self._session = self._create_session()
        self._base = self._prepare_base()

    def __enter__(self):
        """Context manager entry."""
        self._session.begin_nested()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager close session."""
        if exception_type:
            self._session.rollback()
        else:
            self._session.commit()
        self.close_session()

    def _create_metadata(self):
        """Create database metadata to for a specific schema.

        Args:
            None
        Returns:
            (sqlalchemy.sql.schema.MetaData): "SQLAlchemy engine metadata"

        """
        return sqlalchemy.MetaData(bind=self._db, schema=self.schema)

    def _create_session(self):
        """Use a sessionmaker factory to create a scoped session."""
        return self._session_registry()

    def close_session(self):
        """Close the database session."""
        self._session.close()

    def _prepare_base(self):
        """
        Prepare base classes.

        Args:
            None
        Returns:
            (sqlalchemy.ext.declarative.api.DeclarativeMeta): "Declaritive metadata object",
        """
        base = automap_base(metadata=self.get_meta())
        base.prepare(self.get_engine(), reflect=True)
        return base

    def get_base(self):
        """
        Return the base classes.

        Args:
            None
        Returns:
            (sqlalchemy.ext.declarative.api.DeclarativeMeta): "Declaritive metadata object",
        """
        return self._base

    def get_session(self):
        """
        Return Koku database connection session.

        Args:
            None
        Returns:
            (sqlalchemy.orm.session.Session): "SQLAlchemy Session object",
        """
        return self._session

    def get_engine(self):
        """
        Return Koku database connection engine.

        Args:
            None
        Returns:
            (sqlalchemy.engine.base.Engine): "SQLAlchemy engine object",
        """
        return self._db

    def get_meta(self):
        """
        Return Koku database metadata connection.

        Args:
            None
        Returns:
            (sqlalchemy.engine.base.MetaData): "SQLAlchemy metadata object",
        """
        return self._meta

    def _get_db_obj_query(self, **filter_args):
        """
        Return the sqlachemy query for this table .

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."
        """
        obj = self._session.query(self._table)
        if filter_args:
            return obj.filter_by(**filter_args)
        return obj

    def does_db_entry_exist(self):
        """
        Return status for the existance of an object in the database.

        Args:
            None
        Returns:
            (Boolean): "True/False",
        """
        return bool(self._get_db_obj_query().first())

    def add(self, use_savepoint=True, **kwargs):
        """
        Add a new row to this table.

        Args:
            use_savepoint (bool) whether a transaction savepoint should be used
            kwargs (Dictionary): Fields containing table attributes.

        Returns:
            (Object): new model object

        """
        new_entry = self._table(**kwargs)
        if use_savepoint:
            self.savepoint(self._session.add, new_entry)
        else:
            self._session.add(new_entry)
        return new_entry

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

        if use_savepoint:
            self.savepoint(self._session.delete, deleteme)
        else:
            self._session.delete(deleteme)

    def commit(self):
        """
        Commit pending database changes.

        Args:
            None
        Returns:
            None
        """
        self._session.commit()

    def savepoint(self, func, *args, **kwargs):
        """Wrap a db access function in a savepoint block.

        For more info, see:
            https://docs.sqlalchemy.org/en/latest/orm/session_transaction.html#using-savepoint

        Args:
            func (bound method) a function reference.
            args (object) function's positional arguments
            kwargs (object) function's keyword arguments
        Returns:
            None

        """
        try:
            with self._session.begin_nested():
                func(*args, **kwargs)
            self._session.commit()
        except sqlalchemy.exc.IntegrityError as exc:
            LOG.warning('query transaction failed: %s', exc)
            self._session.rollback()
