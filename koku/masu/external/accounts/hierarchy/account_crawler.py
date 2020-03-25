#
# Copyright 2020 Red Hat, Inc.
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
"""Account Hierarchy Abstract class."""

import logging

LOG = logging.getLogger(__name__)


class AccountCrawler:
    """Account Crawler Abstract class."""

    def __init__(self, account):
        """
        Object to crawl the org unit structure for accounts to org units.

        Args:
            role_arn (String): AWS IAM RoleArn
        """
        self.account = account
        self.schema = account.get("schema_name")

    def crawl_account_hierarchy(self):
        LOG.warn("This method must be overriden.")
