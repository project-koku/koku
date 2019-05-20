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
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface


# pylint: disable=too-few-public-methods
class CURAccountsDB(CURAccountsInterface):
    """Provider interface defnition."""

    def get_accounts_from_source(self):
        """
        Retrieve all accounts from the Koku database.

        This will return a list of dicts for the Orchestrator to use to access reports.

        Args:
            None

        Returns:
            ([{}]) : A list of dicts

        """
        accounts = []
        with ProviderCollector() as collector:
            all_providers = collector.get_providers()
            for provider in all_providers:
                account = {
                    'authentication': provider.api_providerauthentication.provider_resource_name,
                    'customer_name': provider.api_customer.schema_name,
                    'billing_source': None,
                    'provider_type': provider.type,
                    'schema_name': provider.api_customer.schema_name,
                    'provider_uuid': provider.uuid
                }
                if provider.api_providerbillingsource:
                    account['billing_source'] = provider.api_providerbillingsource.bucket
                accounts.append(account)
        return accounts
