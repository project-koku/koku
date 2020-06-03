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
"""Cost Usage Report Accounts interface to be used by Masu."""
from abc import ABC
from abc import abstractmethod


class CURAccountsInterface(ABC):
    """Masu interface definition to access Cost of Usage Report accounts."""

    @abstractmethod
    def get_accounts_from_source(self, provider_uuid=None):
        """
        Return a list of all CUR accounts setup in Koku.

        Implemented by an account source class.  Must return a list of
        CostUsageReportAccount objects

        Args:
            provider_uuid (String) - Optional, return specific account

        Returns:
            None

        """
