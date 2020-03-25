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
"""AWS org unit crawler."""
# from tenant_schemas.utils import schema_context
import logging

from masu.util.aws import common as utils
from masu.util.aws.common import get_assume_role_session

LOG = logging.getLogger(__name__)


class AWSOrgUnitCrawler:
    """AWS org unit crawler."""

    def __init__(self, auth_credential, schema):
        """
        Object to crawl the org unit structure for accounts to org units.

        Args:
            role_arn (String): AWS IAM RoleArn
        """
        self._auth_cred = auth_credential
        self._schema = schema
        self.client = self.get_session()
        self.key = "koku_path"

    def get_session(self):
        """
        Set or get a session client for aws organizations

        Args:
            session = aws session
        """
        session = get_assume_role_session(utils.AwsArn(self._auth_cred))
        session_client = session.client("organizations")
        LOG.info("Starting aws organizations session for crawler.")
        return session_client

    def depaginate(self, function, resource_key, **kwargs):
        """
        Depaginates the results of the aws client.

        Args:
            function (AwsFunction): Amazon function name
            resource_key (DataKey): Key to grab from results
            kwargs: Parameters to pass to amazon function

        See: https://gist.github.com/lukeplausin/a3670cd8f115a783a822aa0094015781
        """
        response = function(**kwargs)
        results = response[resource_key]
        while response.get("NextToken", None) is not None:
            response = function(NextToken=response.get("NextToken"), **kwargs)
            results = results + response[resource_key]
        return results

    def get_accounts_per_id(self, parent_id, koku_path):
        """
        List accounts for parents given an aws identifer.

        Args:
            parent_id: unique id for org unit you want to list.
            koku_path: The org unit tree path

        See:
        [1] https://docs.aws.amazon.com/cli/latest/reference/organizations/list-accounts-for-parent.html
        [2] https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/organizations.html
        """
        LOG.info("Obtaining accounts for organizational unit: %s" % parent_id)
        results = []
        child_accounts = self.depaginate(
            function=self.client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
        )
        for act_info in child_accounts:
            act_info[self.key] = koku_path + ("&%s" % act_info["Id"])
            results.append(act_info)
        return results

    def get_root_ou(self):
        """
        Gets the root org unit and preps it for the recursive crawl.
        """
        root_ou = self.client.list_roots()["Roots"][0]
        root_ou[self.key] = root_ou["Id"]
        LOG.info("Obtained the root identifier: %s" % (root_ou["Id"]))
        return root_ou

    def crawl_org_for_acts(self, ou=None):
        """
        Recursively crawls the org units and accounts.

        Args:
            ou (dict): A return from aws client that includes the Id
        """
        if not ou:
            ou = self.get_root_ou()
        results = [ou]
        ou_pager = self.client.get_paginator("list_organizational_units_for_parent")
        for sub_ou in ou_pager.paginate(ParentId=ou["Id"]).build_full_result().get("OrganizationalUnits"):
            LOG.info("Organizational unit found during crawl: %s" % (sub_ou["Id"]))
            if ou.get(self.key):
                sub_ou[self.key] = ou[self.key] + ("&%s" % sub_ou["Id"])
            else:
                sub_ou[self.key] = ou["Id"] + ("&%s" % sub_ou["Id"])
            results.extend(self.crawl_org_for_acts(sub_ou))
        results.extend(self.get_accounts_per_id(ou["Id"], ou[self.key]))
        return results
