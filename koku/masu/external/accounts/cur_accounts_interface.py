#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
