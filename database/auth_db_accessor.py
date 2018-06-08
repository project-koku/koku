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
"""Accessor for Provider Authentication from koku database."""


from masu.database.koku_database_access import KokuDBAccess


class AuthDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Authentication Data."""

    def __init__(self, auth_id, schema='public'):
        """
        Establish Authentication Group database connection.

        Args:
            auth_id      (String) the authentication group unique database id
            schema       (String) database schema (i.e. public or customer tenant value)
        """
        super().__init__(schema)
        self._auth_id = auth_id
        self._auth_group = self.get_base().classes.auth_group

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the authentication object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."
        """
        obj = self.get_session().query(self._auth_group).filter_by(id=self._auth_id)
        return obj

    def get_name(self):
        """
        Return the name for the authentication group.

        Args:
            None
        Returns:
            (String): "Customer Name",
                    example: "Test Customer"
        """
        obj = self._get_db_obj_query().first()
        return obj.name
