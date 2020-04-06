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

from django.db import transaction
from tenant_schemas.utils import schema_context

from masu.external.accounts.hierarchy.account_crawler import AccountCrawler
from masu.external.date_accessor import DateAccessor
from masu.util.aws import common as utils
from reporting.provider.aws.models import AWSOrganizationalUnit

LOG = logging.getLogger(__name__)

# TODO: define a new exception and do try catch


class AWSOrgUnitCrawler(AccountCrawler):
    """AWS org unit crawler."""

    def __init__(self, account):
        """
        Object to crawl the org unit structure for accounts to org units.

        Args:
            role_arn (String): AWS IAM RoleArn
        """
        super().__init__(account)
        self._auth_cred = self.account.get("authentication")
        self.client = None

    def _init_session(self):
        """
        Set or get a session client for aws organizations

        Args:
            session = aws session
        """
        session = utils.get_assume_role_session(utils.AwsArn(self._auth_cred))
        session_client = session.client("organizations")
        LOG.info("Starting aws organizations session for crawler.")
        self.client = session_client

    def _depaginate(self, function, resource_key, **kwargs):
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

    def _crawl_accounts_per_id(self, ou, prefix):
        """
        List accounts for parents given an aws identifer.

        Args:
            parent_id: unique id for org unit you want to list.
            prefix: The org unit tree path

        See:
        [1] https://docs.aws.amazon.com/cli/latest/reference/organizations/list-accounts-for-parent.html
        [2] https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/organizations.html
        """
        parent_id = ou.get("Id")
        LOG.info("Obtaining accounts for organizational unit: %s" % parent_id)
        child_accounts = self._depaginate(
            function=self.client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
        )
        for act_info in child_accounts:
            self._save_aws_org_method(ou.get("Name", ou.get("Id")), ou.get("Id"), prefix, act_info.get("Id"))

    def _crawl_org_for_acts(self, ou, prefix):
        """
        Recursively crawls the org units and accounts.

        Args:
            ou (dict): A return from aws client that includes the Id
        """

        # Save entry for current OU
        self._save_aws_org_method(ou.get("Name", ou.get("Id")), ou.get("Id"), prefix, None)
        try:

            # process accounts for this org unit
            self._crawl_accounts_per_id(ou, prefix)

            # recurse and look for sub org units
            ou_pager = self.client.get_paginator("list_organizational_units_for_parent")
            for sub_ou in ou_pager.paginate(ParentId=ou.get("Id")).build_full_result().get("OrganizationalUnits"):
                new_prefix = prefix + ("&%s" % sub_ou.get("Id"))
                LOG.info("Organizational unit found during crawl: %s" % (sub_ou.get("Id")))
                self._crawl_org_for_acts(sub_ou, new_prefix)
        except Exception:
            LOG.exception(
                "Failure processing org unit.  Account schema {} and org_unit_id {}".format(self.schema, ou.get("Id"))
            )

    def _save_aws_org_method(self, unit_name, unit_id, unit_path, account_id=None):
        """
        Recursively crawls the org units and accounts.

        Args:
            ou (dict): A return from aws client that includes the Id
        """
        LOG.info(
            "Saving account or org unit: unit_name=%s, unit_id=%s, unit_path=%s, account_id=%s"
            % (unit_name, unit_id, unit_path, account_id)
        )
        with schema_context(self.schema):
            row, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=unit_name, org_unit_id=unit_id, org_unit_path=unit_path, account_id=account_id
            )
            if created:
                row.created_timestamp = DateAccessor().today()
                row.save()

    @transaction.atomic
    def crawl_account_hierarchy(self):
        self._init_session()
        root_ou = self.client.list_roots()["Roots"][0]
        LOG.info("Obtained the root identifier: %s" % (root_ou["Id"]))

        self._crawl_org_for_acts(root_ou, root_ou.get("Id"))
