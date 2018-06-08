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

from abc import ABC, abstractmethod

import sqlalchemy
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session

from masu.config import Config


class KokuDBAccess(ABC):
    """Base Class to connect to the koku database."""

    def __init__(self, schema):
        """
        Establish database connection.

        Args:
            schema       (String) database schema (i.e. public or customer tenant value)
        """
        self.schema = schema
        self._db, self._meta = self._connect_db()
        self._session = Session(self._db)

        self._base = self._prepare_base()

    def _connect_db(self):
        """
        Connect to koku database.

        Args:
            None
        Returns:
            (sqlalchemy.engine.base.Engine): "SQLAlchemy engine object",
            (sqlalchemy.sql.schema.MetaData): "SQLAlchemy engine metadata"
        """
        engine = sqlalchemy.create_engine(Config.SQLALCHEMY_DATABASE_URI, client_encoding='utf8')
        meta = sqlalchemy.MetaData(bind=engine, schema=self.schema)
        return engine, meta

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

    @abstractmethod
    def _get_db_obj_query(self):  # pragma: no cover
        """
        Abstract method for database object query to be implemented by subclasses.

        Args:
            None
        Returns:
            None
        """
        pass

    def does_db_entry_exist(self):
        """
        Return status for the existance of an object in the database.

        Args:
            None
        Returns:
            (Boolean): "True/False",
        """
        return bool(self._get_db_obj_query().first())
