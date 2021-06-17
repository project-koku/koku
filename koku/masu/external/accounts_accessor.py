#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider external interface for koku to consume."""
import logging

from masu.config import Config
from masu.exceptions import CURAccountsInterfaceError
from masu.external import POLL_INGEST
from masu.external.accounts.db.cur_accounts_db import CURAccountsDB
from masu.util import common as utils
from masu.util.ocp import common as ocp_utils

LOG = logging.getLogger(__name__)


class AccountsAccessorError(Exception):
    """Cost Usage Report Accounts error."""


class AccountsAccessor:
    """Interface for masu to use to get CUR accounts."""

    def __init__(self, source_type=Config.ACCOUNT_ACCESS_TYPE):
        """Set the CUR accounts external source."""
        self.source_type = source_type.lower()
        self.source = self._set_source()
        if not self.source:
            raise AccountsAccessorError("Invalid source type specified.")

    def _set_source(self):
        """
        Create the provider service object.

        Set what source should be used to get CUR accounts.

        Args:
            None

        Returns:
            (Object) : Some object that is a child of CURAccountsInterface

        """
        if self.source_type == "db":
            return CURAccountsDB()

        return None

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
            log_statement = (
                f"Polling for\n"
                f' schema_name: {account.get("schema_name")}\n'
                f' provider: {account.get("provider_type")}\n'
                f' account (provider uuid): {account.get("provider_uuid")}'
            )
            LOG.info(log_statement)
            return True
        return False

    def get_accounts(self, provider_uuid=None):
        """
        Return all of the CUR accounts setup in Koku.

        The CostUsageReportAccount object has everything needed to download CUR files.

        Args:
            None

        Returns:
            ([{}]) : A list of account access dictionaries

        """
        try:
            accounts = self.source.get_accounts_from_source(provider_uuid)
        except CURAccountsInterfaceError as error:
            raise AccountsAccessorError(str(error))

        return accounts
