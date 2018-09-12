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
"""Accessor for Account alias information from koku database."""


from masu.database.koku_database_access import KokuDBAccess


class AccountAliasAccessor(KokuDBAccess):
    """Class to interact with the koku database for account allias information."""

    def __init__(self, account_id, schema):
        """
        Establish account alias database connection.

        Args:
            account_id   (String) account id
            schema       (String) database schema (i.e. public or customer tenant value)
        """
        super().__init__(schema)
        self._account_id = account_id
        self._account_alias = self.get_base().classes.reporting_awsaccountalias

        if self.does_db_entry_exist() is False:
            self.add(self._account_id)

        self._obj = self._get_db_obj_query().first()

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the customer object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ...",
        """
        obj = self.get_session().query(self._account_alias).filter_by(account_id=self._account_id)
        return obj

    def commit(self):
        """
        Commit pending database changes.

        Args:
            None
        Returns:
            None
        """
        self._session.commit()

    def add(self, account_id):
        """
        Add a new row to the CUR stats database.

        Args:
            (String): Account ID

        Returns:
            None

        """
        new_entry = self._account_alias(account_id=account_id)
        self._session.add(new_entry)

    def set_account_alias(self, alias):
        """
        Save the account alias for the account.

        Args:
            alias (String): account alias for the given account.
        Returns:
            None

        """
        self._obj.account_alias = alias
