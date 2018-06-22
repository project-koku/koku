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
"""Database source impelmentation to provide all CUR accounts for CURAccounts access."""

from masu.database.provider_collector import ProviderCollector
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.accounts.cost_usage_report_account import CostUsageReportAccount
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface


# pylint: disable=too-few-public-methods
class CURAccountsDB(CURAccountsInterface):
    """Provider interface defnition."""

    def get_accounts_from_source(self):
        """
        Retrieve all CUR accounts from the database managed by Koku.

        This will return a list of CostUsageReportAccount objects for the
        CUR Orchestrator to use to download CUR reports.

        Args:
            None

        Returns:
            ([CostUsageReportAcount]) : A list of Cost Usage Report Account objects

        """
        collector = ProviderCollector()
        all_providers = collector.get_providers()

        cur_accounts = []
        for provider in all_providers:
            provider_accessor = ProviderDBAccessor(provider.uuid)
            auth_credential = provider_accessor.get_authentication()
            billing_source = provider_accessor.get_billing_source()
            customer_name = provider_accessor.get_customer_name()
            provider_type = provider_accessor.get_type()
            schema_name = provider_accessor.get_schema()
            cur_account = CostUsageReportAccount(auth_credential,
                                                 billing_source,
                                                 customer_name,
                                                 provider_type,
                                                 schema_name)
            cur_accounts.append(cur_account)
        return cur_accounts
