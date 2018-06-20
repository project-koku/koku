#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Provider external interface for koku to consume."""


from masu.external.accounts.db.cur_accounts_db import CURAccountsDB


class AccountsAccessorError(Exception):
    """Cost Usage Report Accounts error."""

    pass


# pylint: disable=too-few-public-methods
class AccountsAccessor:
    """Interface for masu to use to get CUR accounts."""

    def __init__(self, source_type='db'):
        """Set the CUR accounts external source."""
        self.source_type = source_type
        self.source = self._set_source()
        if not self.source:
            raise AccountsAccessorError('Invalid source type specified.')

    def _set_source(self):
        """
        Create the provider service object.

        Set what source should be used to get CUR accounts.

        Args:
            None

        Returns:
            (Object) : Some object that is a child of CURAccountsInterface

        """
        if self.source_type == 'db':
            return CURAccountsDB()
        return None

    def get_accounts(self):
        """
        Return all of the CUR accounts setup in Koku.

        The CostUsageReportAccount object has everything needed to download CUR files.

        Args:
            None

        Returns:
            ([CostUsageReportAcount]) : A list of Cost Usage Report Account objects

        """
        return self.source.get_accounts_from_source()
