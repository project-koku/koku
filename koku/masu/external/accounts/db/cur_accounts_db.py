#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database source implementation to provide all CUR accounts for CURAccounts access."""
import logging

from api.common import log_json
from api.models import Customer
from api.models import Provider
from api.provider.provider_manager import ProviderManager
from api.utils import DateHelper
from masu.config import Config
from masu.database.provider_collector import ProviderCollector
from masu.external.accounts.cur_accounts_interface import CURAccountsInterface
from masu.processor import is_source_disabled

LOG = logging.getLogger(__name__)
dh = DateHelper()


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

    def is_source_pollable(self, provider, provider_uuid=None):
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
        # This check is needed for OCP ingress reports
        if not provider_uuid:
            poll_timestamp = provider.polling_timestamp
            timer = Config.POLLING_TIMER
            if poll_timestamp is not None:
                if ((dh.now_utc - poll_timestamp).seconds) < timer:
                    return False
        return True

    def set_large_customer(self, provider):
        """checks and sets large customer flag."""
        provider_manager = ProviderManager(provider.uuid)
        count = provider_manager.get_active_provider_count_for_customer(provider.customer_id)
        large_customer = False
        if count > Config.LARGE_CUSTOMER_PROVIDER_COUNT:
            large_customer = True
        customer_rec = Customer.objects.filter(id=provider.customer_id).get()
        if customer_rec.large_customer != large_customer:
            customer_rec.large_customer = large_customer
            LOG.info(
                log_json(
                    msg="setting if customer is large",
                    provider_type=provider.type,
                    provider_uuid=provider.uuid,
                    schema=provider.customer_id,
                    is_customer_large=customer_rec.large_customer,
                )
            )
            customer_rec.save()

    def get_accounts_from_source(self, provider_uuid=None, provider_type=None, scheduled=False):
        """
        Retrieve all accounts from the Koku database.

        This will return a list of dicts for the Orchestrator to use to access reports.

        Args:
            provider_uuid (String) - Optional, return specific account

        Returns:
            ([{}]) : A list of dicts

        """
        accounts = []
        batch_size = Config.POLLING_BATCH_SIZE
        with ProviderCollector() as collector:
            all_providers = collector.get_provider_uuid_map()
            provider = all_providers.get(str(provider_uuid))
            if provider_uuid and not provider:
                LOG.info(log_json(msg="provider does not exist", provider_uuid=provider_uuid))
                return []
            elif provider_uuid and provider:
                if self.is_source_pollable(provider, provider_uuid):
                    return [self.get_account_information(provider)]
                return []

            LOG.info(
                log_json(
                    msg="looping through providers polling for accounts",
                    scheduled=scheduled,
                )
            )

            for _, provider in all_providers.items():
                if len(accounts) < batch_size:
                    self.set_large_customer(provider)
                    if scheduled and provider.type == Provider.PROVIDER_OCP:
                        continue
                    if provider_type and provider_type not in provider.type:
                        continue
                    if self.is_source_pollable(provider):
                        accounts.append(self.get_account_information(provider))
                        # Update provider polling time.
                        provider.polling_timestamp = dh.now_utc
                        provider.save()
                        LOG.info(
                            log_json(
                                msg="adding provider to polling batch",
                                provider_type=provider.type,
                                provider_uuid=provider.uuid,
                                schema=provider.customer_id,
                                polling_count=len(accounts),
                                polling_batch_count=batch_size,
                            )
                        )
                else:
                    break
        return accounts
