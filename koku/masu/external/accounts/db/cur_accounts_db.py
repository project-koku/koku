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
            "customer_name": getattr(provider.customer, "schema_name", None),
            "credentials": getattr(provider.authentication, "credentials", None),
            "data_source": getattr(provider.billing_source, "data_source", None),
            "provider_type": provider.type,
            "schema_name": getattr(provider.customer, "schema_name", None),
            "provider_uuid": provider.uuid,
        }

    def get_accounts_from_source(self, provider_uuid=None, provider_type=None):
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
            if provider_uuid and not provider:
                LOG.info(f"Provider for uuid {provider_uuid} does not exist its likely it has been deleted.")
                return []
            elif provider_uuid and provider:
                if provider.active and not provider.paused:
                    return [self.get_account_information(provider)]
                LOG.info(
                    f"Provider {provider.uuid} is active={provider.active} "
                    f"or paused={provider.paused}. Processing suspended..."
                )
                return []

            for _, provider in all_providers.items():
                if provider.active is False or provider.paused:
                    LOG.info(
                        f"Provider {provider.uuid} is active={provider.active} "
                        f"or paused={provider.paused}. Processing suspended..."
                    )
                    continue
                if provider_type and provider_type not in provider.type:
                    continue
                accounts.append(self.get_account_information(provider))
            msg = f"""Looping through providers polling for:
                provider_uuid: {provider_uuid},
                provider_type: {provider_type}
            """
            LOG.info(msg)
        return accounts
