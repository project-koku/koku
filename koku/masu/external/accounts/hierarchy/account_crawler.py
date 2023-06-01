#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Account Hierarchy Abstract class."""
import logging
from abc import ABC
from abc import abstractmethod

LOG = logging.getLogger(__name__)


class AccountCrawler(ABC):
    """Account Crawler Abstract class."""

    def __init__(self, account):
        """
        Object to crawl the org unit structure for accounts to org units.

        Args:
            role_arn (String): AWS IAM RoleArn
        """
        self.account = account
        self.schema_name = account.get("schema_name")

    @abstractmethod
    def crawl_account_hierarchy(self):
        """
        Crawl the account hierarchy structure to get organizational information.

        Returns:
            None

        """
