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


class AWSOrgUnitCrawler(AccountCrawler):
    """AWS org unit crawler."""

    def __init__(self, account):
        """
        Object to crawl the org unit structure for accounts to org units.

        Args:
            account (String): AWS IAM RoleArn
        """
        super().__init__(account)
        self._auth_cred = self.account.get("authentication")
        self._date_accessor = DateAccessor()
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
        Returns:
            (list): List of accounts

        See: https://gist.github.com/lukeplausin/a3670cd8f115a783a822aa0094015781
        """
        response = function(**kwargs)
        results = response[resource_key]
        while response.get("NextToken", None) is not None:
            response = function(NextToken=response.get("NextToken"), **kwargs)
            results = results + response[resource_key]
        return results

    def _crawl_accounts_per_id(self, ou, prefix, level):
        """
        List accounts for parents given an aws identifer.

        Args:
            ou: org unit you want to list.
            prefix: The org unit tree path
        Returns:
            (list): List of accounts for an org unit

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
            self._save_aws_org_method(ou, prefix, level, act_info.get("Id"))

    def _crawl_org_for_accounts(self, ou, prefix, level):
        """
        Recursively crawls the org units and accounts.

        Args:
            ou (dict): A return from aws client that includes the Id
            prefix (str): The org unit path prefix
            level (int): The level of the tree
        """

        # Save entry for current OU
        self._save_aws_org_method(ou, prefix, level)
        try:

            # process accounts for this org unit
            self._crawl_accounts_per_id(ou, prefix, level)
            level = level + 1
            # recurse and look for sub org units
            ou_pager = self.client.get_paginator("list_organizational_units_for_parent")
            for sub_ou in ou_pager.paginate(ParentId=ou.get("Id")).build_full_result().get("OrganizationalUnits"):
                new_prefix = prefix + ("&%s" % sub_ou.get("Id"))
                LOG.info("Organizational unit found during crawl: %s" % (sub_ou.get("Id")))
                self._crawl_org_for_accounts(sub_ou, new_prefix, level)

        except Exception:
            LOG.exception(
                "Failure processing org unit.  Account schema {} and org_unit_id {}".format(self.schema, ou.get("Id"))
            )

    def _save_aws_org_method(self, ou, unit_path, level, account_id=None):
        """
        Recursively crawls the org units and accounts.

        Args:
            ou (dict): The aws organizational unit dictionary
            unit_path (str): The tree path to the org unit
            level (int): The level of the node in the org data tree
            account_id (str): The AWS account number.  If internal node, None
        Returns:
            (AWSOrganizationalUnit): That was created or looked up
        """
        unit_name = ou.get("Name", ou.get("Id"))
        unit_id = ou.get("Id")
        with schema_context(self.schema):
            obj, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=unit_name,
                org_unit_id=unit_id,
                org_unit_path=unit_path,
                account_id=account_id,
                level=level,
            )
            if created:
                # only log it was saved if was created to reduce logging on everyday calls
                LOG.info(
                    "Saving account or org unit: unit_name=%s, unit_id=%s, unit_path=%s, account_id=%s, level=%s"
                    % (unit_name, unit_id, unit_path, account_id, level)
                )
            return obj

    def _delete_aws_account(self, account_id):
        """
        Marks an account deleted.

        Args:
            account_id (str): The AWS account number.
        Returns:
            QuerySet(AWSOrganizationalUnit): That were marked deleted
        """
        LOG.info("Marking account deleted: account_id=%s" % (account_id))
        with schema_context(self.schema):
            accounts = AWSOrganizationalUnit.objects.filter(account_id=account_id)
            # The can be multiple records for a single accounts due to changes in org structure
            for account in accounts:
                account.deleted_timestamp = self._date_accessor.today().strftime("%Y-%m-%d")
                account.save()
            return accounts

    def _delete_aws_org_unit(self, org_unit_id):
        """
        Marks an account deleted.

        Args:
            org_unit_id (str): The AWS organization unit id.
        Returns:
            QuerySet(AWSOrganizationalUnit): That were marked deleted
        """
        LOG.info("Marking org unit deleted deleted: org_unit_id=%s" % (org_unit_id))
        with schema_context(self.schema):
            accounts = AWSOrganizationalUnit.objects.filter(org_unit_id=org_unit_id)
            # The can be multiple records for a single accounts due to changes in org structure
            for account in accounts:
                account.deleted_timestamp = self._date_accessor.today().strftime("%Y-%m-%d")
                account.save()
            return accounts

    @transaction.atomic
    def crawl_account_hierarchy(self):
        self._init_session()
        root_ou = self.client.list_roots()["Roots"][0]
        LOG.info("Obtained the root identifier: %s" % (root_ou["Id"]))
        self._crawl_org_for_accounts(root_ou, root_ou.get("Id"), level=0)

    def _compute_org_structure_for_day(self, start_date, end_date=None):
        """Compute the org structure for a day."""
        # On a particular day (e.g. March 1, 2020)
        # 1. Filter out nodes deleted on OR before date (e.g on or before March 1, 2020)
        # 2. From that set, find the newest (using created timestamp) nodes
        # 3. Build a dictionary where key= org_id+account_id (empty string for account_id if internal node)
        #    and value = django record (so we can do updates if needed)
        # AWSOrganizationalUnit.objects.filter(deleted_timestamp__gte=date)
        if not end_date:
            end_date = start_date
        with schema_context(self.schema):
            LOG.info("#" * 120)
            LOG.info(f"Tree for {start_date} to {end_date}")
            # Remove org units delete on date or before
            aws_node_qs = AWSOrganizationalUnit.objects.exclude(deleted_timestamp__lte=start_date)

            # Remove org units created after date
            aws_node_qs = aws_node_qs.exclude(created_timestamp__gt=end_date)

            aws_org_units = (
                aws_node_qs.filter(account_id__isnull=True)
                .order_by("org_unit_id", "-created_timestamp")
                .distinct("org_unit_id")
            )
            aws_accounts = (
                aws_node_qs.filter(account_id__isnull=False)
                .order_by("account_id", "-created_timestamp")
                .distinct("account_id")
            )

            LOG.info("$$$$ BEGIN PRINT TREE $$$$")
            for org_unit in aws_org_units:
                LOG.info(org_unit)
            for org_unit in aws_accounts:
                LOG.info(org_unit)
            LOG.info("$$$$ END PRINT TREE $$$$")
