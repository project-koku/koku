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
from datetime import timedelta

from django.db import transaction
from tenant_schemas.utils import schema_context

from masu.external.accounts.hierarchy.account_crawler import AccountCrawler
from masu.external.date_accessor import DateAccessor
from masu.util.aws import common as utils
from reporting.provider.aws.models import AWSAccountAlias
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
        self._client = None
        self._account_alias_map = None
        self._structure_yesterday = None

    @transaction.atomic
    def crawl_account_hierarchy(self):
        self._init_session()
        self._build_accout_alias_map()

        self._compute_org_structure_yesterday()
        root_ou = self._client.list_roots()["Roots"][0]
        LOG.info("Obtained the root identifier: %s" % (root_ou["Id"]))
        self._crawl_org_for_accounts(root_ou, root_ou.get("Id"), level=0)
        self._mark_nodes_deleted()

    def _mark_nodes_deleted(self):
        today = self._date_accessor.today()
        # Mark everything that is dict as deleted
        with schema_context(self.schema):
            for _, org_unit in self._structure_yesterday.items():
                org_unit.deleted_timestamp = today
                org_unit.save()

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
            ou_pager = self._client.get_paginator("list_organizational_units_for_parent")
            for sub_ou in ou_pager.paginate(ParentId=ou.get("Id")).build_full_result().get("OrganizationalUnits"):
                new_prefix = prefix + ("&%s" % sub_ou.get("Id"))
                LOG.info("Organizational unit found during crawl: %s" % (sub_ou.get("Id")))
                self._crawl_org_for_accounts(sub_ou, new_prefix, level)

        except Exception:
            LOG.exception(
                "Failure processing org unit.  Account schema {} and org_unit_id {}".format(self.schema, ou.get("Id"))
            )

    def _init_session(self):
        """
        Set or get a session client for aws organizations

        Args:
            session = aws session
        """
        session = utils.get_assume_role_session(utils.AwsArn(self._auth_cred))
        session_client = session.client("organizations")
        LOG.info("Starting aws organizations session for crawler.")
        self._client = session_client

    def _depaginate_account_list(self, function, resource_key, **kwargs):
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
        child_accounts = self._depaginate_account_list(
            function=self._client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
        )
        for act_info in child_accounts:
            self._save_aws_org_method(ou, prefix, level, act_info)

    def _save_aws_org_method(self, ou, unit_path, level, account=None):
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
        account_alias = None
        account_id = None

        with schema_context(self.schema):
            # This is a leaf node
            if account:
                # Look for an existing alias
                account_id = account.get("Id")
                account_name = account.get("Name")
                account_alias = self._account_alias_map.get(account_id)
                if not account_alias:
                    # Create a new account alias (not cached
                    account_alias, created = AWSAccountAlias.objects.get_or_create(account_id=account_id)
                    self._account_alias_map[account_id] = account_alias
                    LOG.info(f"Saving account alias {account_alias} (created={created})")

                if account_name and account_alias.account_alias != account_name:
                    # The name was not set or changed since last scan.
                    LOG.info(
                        "Updating account alias for account_id=%s, old_account_alias=%s, new_account_alias=%s"
                        % (account_id, account_alias.account_alias, account_name)
                    )
                    account_alias.account_alias = account_name
                    account_alias.save()

            org_unit, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=unit_name,
                org_unit_id=unit_id,
                org_unit_path=unit_path,
                account_alias=account_alias,
                level=level,
            )

            # Remove key since we have seen it
            lookup_key = self._create_lookup_key(unit_id, account_id)
            self._structure_yesterday.pop(lookup_key, None)

            if created:
                # only log it was saved if was created to reduce logging on everyday calls
                LOG.info(
                    "Saving account or org unit: unit_name=%s, unit_id=%s, unit_path=%s, account_alias=%s, level=%s"
                    % (unit_name, unit_id, unit_path, account_alias, level)
                )
            return org_unit

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
            account_alias = AWSAccountAlias.objects.filter(account_id=account_id).first()
            accounts = AWSOrganizationalUnit.objects.filter(account_alias=account_alias)
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

    def _build_accout_alias_map(self):
        """
        Builds a map of account_id to account alias for foreign keys

        Returns:
            dict: account_id to AWSAccountAlias
        """
        self._account_alias_map = {}
        with schema_context(self.schema):
            for alias in AWSAccountAlias.objects.all():
                self._account_alias_map[alias.account_id] = alias

    def _compute_org_structure_yesterday(self):
        """
        Construct the tree structure for yesterday

        Returns:
            dict: key built of org_unit (if account is none) or org_unit and account number to
            django AWSOrganizationalUnit model objects.
        """
        yesterday = (self._date_accessor.today() - timedelta(1)).strftime("%Y-%m-%d")
        self._structure_yesterday = self._compute_org_structure_interval(yesterday)

    def _compute_org_structure_interval(self, start_date, end_date=None):
        """
        Construct the tree structure for an interval

        Args:
            start_date (datetime.datetime): Interval start time.
            end_date (datetime.datetime): Interval end time.
        Returns:
            dict: key built of org_unit (if account is none) or org_unit and account number to
            django AWSOrganizationalUnit model objects.
        """

        if not end_date:
            end_date = start_date
        with schema_context(self.schema):
            LOG.info(f"Tree for {start_date} to {end_date}")
            # Remove org units delete on date or before
            aws_node_qs = AWSOrganizationalUnit.objects.exclude(deleted_timestamp__lte=start_date)

            # Remove org units created after date
            aws_node_qs = aws_node_qs.exclude(created_timestamp__gt=end_date)

            aws_org_units = (
                aws_node_qs.filter(account_alias__isnull=True)
                .order_by("org_unit_id", "-created_timestamp")
                .distinct("org_unit_id")
            )
            aws_accounts = (
                aws_node_qs.filter(account_alias__isnull=False)
                .order_by("account_alias", "-created_timestamp")
                .distinct("account_alias")
            )

            structure = {}
            for org_unit in aws_org_units:
                structure[self._create_lookup_key(org_unit.org_unit_id)] = org_unit
            for org_unit in aws_accounts:
                structure[self._create_lookup_key(org_unit.org_unit_id, org_unit.account_alias.account_id)] = org_unit
            return structure

    def _create_lookup_key(self, unit_id, account_id=None):
        """
        Construct the lookup key for the _structure_yesterday tree

        Args:
            unit_id (str): The AWS organization unit id.
            account_id (str): The AWS account id or None if it's an internal node
        Returns:
            str: key to lookup org units and accounts
        """
        if account_id:
            lookup_key = f"{unit_id}&{account_id}"
        else:
            lookup_key = f"{unit_id}"

        return lookup_key
