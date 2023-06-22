#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database source implementation to provide all CUR accounts for CURAccounts access."""
import logging

from api.common import log_json
from masu.database.provider_collector import ProviderCollector
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface
from masu.processor import is_source_disabled

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

    def source_is_pollable(self, provider):
        """checks to see if a source is pollable."""
        if is_source_disabled(provider.uuid):
            return False
        if provider.active is False or provider.paused:
            LOG.info(
                log_json(
                    msg="processing suspended for provider",
                    provider_uuid=provider.uuid,
                    active=provider.active,
                    paused=provider.paused,
                )
            )
            return False
        return True

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
                LOG.info(log_json(msg="provider does not exist", provider_uuid=provider_uuid))
                return []
            elif provider_uuid and provider:
                if self.source_is_pollable(provider):
                    return [self.get_account_information(provider)]
                return []

            for _, provider in all_providers.items():
                if provider_type and provider_type not in provider.type:
                    continue
                if self.source_is_pollable(provider):
                    accounts.append(self.get_account_information(provider))

            LOG.info(
                log_json(
                    msg="looping through providers polling for accounts",
                    provider_uuid=provider_uuid,
                    provider_type=provider_type,
                )
            )
        return accounts
