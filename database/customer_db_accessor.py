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


from masu.database.koku_database_access import KokuDBAccess


class CustomerDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for Provider Billing Source Data."""

    def __init__(self, customer_id, schema='public'):
        """
        Establish Provider Billing Source database connection.

        Args:
            customer_id  (String) the customer unique database id
            schema       (String) database schema (i.e. public or customer tenant value)
        """
        super().__init__(schema)
        self._customer_id = customer_id
        self._customer = self.get_base().classes.api_customer

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the customer object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ...",
        """
        obj = self.get_session().query(self._customer).filter_by(group_ptr_id=self._customer_id)
        return obj

    def get_uuid(self):
        """
        Return the customer uuid.

        Args:
            None
        Returns:
            (String): "UUID v4",
                    example: "edf94475-235e-4b64-ba18-0b81f2de9c9e"
        """
        obj = self._get_db_obj_query().first()
        return obj.uuid

    def get_schema_name(self):
        """
        Return the schema name.

        Args:
            None
        Returns:
            (String): "Schema Name based on customer name",
                    example: "testcustomer"
        """
        obj = self._get_db_obj_query().first()
        return obj.schema_name

    def get_group_ptr_id(self):
        """
        Return the group id for the customer.

        Args:
            None
        Returns:
            (Integer): "Integer value to map customer to group.",
                    example: "1"
        """
        obj = self._get_db_obj_query().first()
        return obj.group_ptr_id
