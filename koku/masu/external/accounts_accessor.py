#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider external interface for koku to consume."""
import logging

from api.common import log_json
from api.models import Provider
from api.models import Tenant
from api.utils import DateHelper
from masu.config import Config
from masu.external import POLL_INGEST
from masu.processor import is_source_disabled
from masu.util import common as utils
from masu.util.ocp import common as ocp_utils

LOG = logging.getLogger(__name__)
dh = DateHelper()


def get_provider_uuid_map(providers):
    return {str(provider.uuid): provider for provider in providers}


def get_all_providers():
    return Provider.objects.select_related("authentication", "billing_source", "customer")


def get_pollable_providers(filters: dict):
    return get_all_providers().filter(active=True, paused=False, **filters)


def get_account_from_uuid(provider_uuid):
    if provider := get_all_providers().filter(uuid=provider_uuid).first():
        return get_account_information(provider)
    else:
        raise AccountsAccessorError("provider not found")


def get_all_tenants():
    return Tenant.objects.exclude(schema_name__in=["public", "template0"]).values_list("schema_name", flat=True)


def get_account_information(provider) -> dict:
    """Return account information in dictionary."""
    return {
        "customer_name": getattr(provider.customer, "schema_name", None),
        "credentials": getattr(provider.authentication, "credentials", None),
        "data_source": getattr(provider.billing_source, "data_source", None),
        "provider_type": provider.type,
        "schema_name": getattr(provider.customer, "schema_name", None),
        "provider_uuid": provider.uuid,
    }


def is_source_pollable(provider, provider_uuid=None) -> bool:
    """checks to see if a source is pollable."""
    if is_source_disabled(provider.uuid):
        return False

    # This check is needed for OCP ingress reports
    if not provider_uuid:
        poll_timestamp = provider.polling_timestamp
        if poll_timestamp is not None and ((dh.now_utc - poll_timestamp).seconds) < Config.POLLING_TIMER:
            return False
    return True


def get_accounts_from_source(provider_type=None, scheduled=False) -> list:
    """
    Retrieve all accounts from the Koku database.

    This will return a list of dicts for the Orchestrator to use to access reports.

    Args:
        provider_uuid (String) - Optional, return specific account

    Returns:
        ([{}]) : A list of dicts

    """
    accounts = []

    filters = {}
    if provider_type:
        filters["type"] = provider_type

    pollable_providers = get_pollable_providers(filters)

    if scheduled:
        pollable_providers = pollable_providers.exclude(provider_type=Provider.PROVIDER_OCP)
    all_providers = get_provider_uuid_map(pollable_providers)

    LOG.info(
        log_json(
            msg="looping through providers polling for accounts",
            scheduled=scheduled,
        )
    )

    for _, provider in all_providers.items():
        if len(accounts) >= Config.POLLING_BATCH_SIZE:
            break
        if not is_source_pollable(provider):
            continue
        accounts.append(get_account_information(provider))
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
                polling_batch_count=Config.POLLING_BATCH_SIZE,
            )
        )

    return accounts


class AccountsAccessorError(Exception):
    """Cost Usage Report Accounts error."""


class AccountsAccessor:
    """Interface for masu to use to get CUR accounts."""

    @staticmethod
    def is_polling_account(account):
        """
        Determine if account should be polled to initiate the processing pipeline.

        Account report information can be ingested by either POLLING (hourly beat schedule)
        or by LISTENING (kafka event-driven).

        There is a development-only use case to be able to force an account to follow the
        polling ingest path.  For Example: OpenShift is a LISTENING provider type but we
        can still side-load data by placing it in the temporary file storage directory on
        the worker.  On the next poll the Orchestrator will look for report updates in this
        directory and proceed with the download/processing steps.

        Args:
            account (dict) - Account dictionary that is retruned by
                             AccountsAccessor().get_accounts()

        Returns:
            (Boolean) : True if provider should be polled for updates.

        """
        if utils.ingest_method_for_provider(
            account.get("provider_type")
        ) == POLL_INGEST or ocp_utils.poll_ingest_override_for_provider(account.get("provider_uuid")):
            LOG.info(
                log_json(
                    msg="polling for account",
                    schema=account.get("schema_name"),
                    provider_type=account.get("provider_type"),
                    provider_uuid=account.get("provider_uuid"),
                )
            )
            return True
        return False

    def get_accounts(self, provider_type=None, scheduled=False):
        """
        Return all of the CUR accounts setup in Koku.

        The CostUsageReportAccount object has everything needed to download CUR files.

        Args:
            None

        Returns:
            ([{}]) : A list of account access dictionaries

        """

        return get_accounts_from_source(provider_type, scheduled)

    def get_account_from_uuid(self, provider_uuid):
        return get_account_from_uuid(provider_uuid)
