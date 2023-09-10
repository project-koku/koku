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
from masu.external import POLL_INGEST
from masu.util import common as utils
from masu.util.ocp import common as ocp_utils

LOG = logging.getLogger(__name__)
dh = DateHelper()


def get_provider_uuid_map(providers):
    return {str(provider.uuid): provider for provider in providers}


def get_all_providers():
    return Provider.objects.select_related("authentication", "billing_source", "customer")


def get_pollable_providers(filters: dict = None, excludes: dict = None):
    if not filters:
        filters = {}
    if not excludes:
        excludes = {}
    return get_all_providers().filter(active=True, paused=False, **filters).exclude(**excludes)


def get_account_from_uuid(provider_uuid):
    if provider := Provider.objects.filter(uuid=provider_uuid).first():
        return provider.account
    else:
        raise AccountsAccessorError("provider not found")


def get_all_tenants():
    return Tenant.objects.exclude(schema_name__in=["public", "template0"]).values_list("schema_name", flat=True)


def get_accounts_from_source(provider_type=None, scheduled=False) -> list:
    """
    Retrieve all accounts from the Koku database.

    This will return a list of dicts for the Orchestrator to use to access reports.

    Args:
        provider_uuid (String) - Optional, return specific account

    Returns:
        ([{}]) : A list of dicts

    """
    filters = {}
    if provider_type:
        filters["type"] = provider_type

    pollable_providers = get_pollable_providers(filters)

    if scheduled:
        pollable_providers = pollable_providers.exclude(provider_type=Provider.PROVIDER_OCP)

    LOG.info(
        log_json(
            msg="looping through providers polling for accounts",
            scheduled=scheduled,
        )
    )

    return [p.account for p in pollable_providers]


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
