#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database source implementation to provide all CUR accounts for CURAccounts access."""
import logging

from masu.database.provider_collector import ProviderCollector
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface

LOG = logging.getLogger(__name__)


class CURAccountsDB(CURAccountsInterface):
    """Provider interface definition."""

    @staticmethod
    def get_account_information(provider):
        """Return account information in dictionary."""
        return {
            "customer_name": provider.customer.schema_name,
            "credentials": provider.authentication.credentials,
            "data_source": provider.billing_source.data_source,
            "provider_type": provider.type,
            "schema_name": provider.customer.schema_name,
            "provider_uuid": provider.uuid,
        }

    def get_accounts_from_source(self, provider_uuid=None):
        """
        Retrieve all accounts from the Koku database.

        This will return a list of dicts for the Orchestrator to use to access reports.

        Args:
            provider_uuid (String) - Optional, return specific account

        Returns:
            ([{}]) : A list of dicts

        """
        accounts = []
        with ProviderCollector() as collector:
            all_providers = collector.get_provider_uuid_map()
            provider = all_providers.get(str(provider_uuid))
            if provider_uuid and provider:
                if provider.active:
                    return [self.get_account_information(provider)]
                else:
                    LOG.info(f"Provider {provider.uuid} is not active. Processing suspended...")
                    return []

            for _, provider in all_providers.items():
                if provider.active is False:
                    LOG.info(f"Provider {provider.uuid} is not active. Processing suspended...")
                    continue
                accounts.append(self.get_account_information(provider))
        return accounts
