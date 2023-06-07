#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Utility functions for inserting a aws org unit tree for testing."""
import logging
from datetime import datetime
from datetime import timedelta

import ciso8601
from django_tenants.utils import schema_context

from masu.database.provider_db_accessor import ProviderDBAccessor
from reporting.provider.aws.models import AWSAccountAlias
from reporting.provider.aws.models import AWSOrganizationalUnit

# from reporting.models import TenantAPIProvider

LOG = logging.getLogger(__name__)


class InsertAwsOrgTreeError(Exception):
    def __init__(self, err_msg):
        self.message = err_msg
        super().__init__(self.message)


class InsertAwsOrgTree:
    """Insert aws org tree abstract class."""

    def __init__(self, schema, provider_uuid, start_date=None):
        self.schema = schema
        self.start_date = start_date
        self.yesterday_accounts = []
        self.yesterday_orgs = []
        self.today_accounts = []
        self.today_orgs = []
        self.account_alias_mapping = {}
        self.provider = self.get_provider(provider_uuid)
        # self.tenant_provider = self.get_tenant_provider(provider_uuid)

    def get_provider(self, provider_uuid):
        """Returns the provider given the provider_uuid."""
        with ProviderDBAccessor(provider_uuid) as provider_accessor:
            return provider_accessor.get_provider()

    # def get_tenant_provider(self, provider_uuid):
    #     """Returns the provider given the provider_uuid."""
    #     with schema_context(self.schema):
    #         return TenantAPIProvider.objects.get(uuid=provider_uuid)

    def calculate_date(self, day_delta):
        """Calculate the date based off of a delta and a range start date."""
        if not self.start_date:
            self.start_date = datetime.today().date()
        if isinstance(self.start_date, str):
            self.start_date = ciso8601.parse_datetime(self.start_date)
        date = self.start_date + timedelta(days=day_delta)
        if isinstance(date, datetime):
            return str(date.date())
        return str(date)

    def _insert_org_sql(self, org_node, date):
        """Inserts the org unit information into the database."""
        with schema_context(self.schema):
            org_unit, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=org_node["org_unit_name"],
                org_unit_id=org_node["org_unit_id"],
                org_unit_path=org_node["org_path"],
                level=org_node["level"],
                account_alias=None,
                provider_id=self.provider.uuid,
            )
            if created:
                org_unit.created_timestamp = date
                org_unit.save()
                LOG.info(
                    f"Creating OU={org_node['org_unit_id']} with path={org_node['org_path']} "
                    f"at level={org_node['level']} on created_timestamp={date}."
                )

    def _insert_account(self, org_node, act_info, date):
        """Inserts the account information in the database."""
        account_alias_id = act_info["account_alias_id"]
        account_alias_name = act_info.get("account_alias_name")
        with schema_context(self.schema):
            if account_alias_name:
                account_alias, created = AWSAccountAlias.objects.get_or_create(
                    account_id=account_alias_id, account_alias=account_alias_name
                )
            else:
                account_alias, created = AWSAccountAlias.objects.get_or_create(account_id=account_alias_id)
            org_unit, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=org_node["org_unit_name"],
                org_unit_id=org_node["org_unit_id"],
                org_unit_path=org_node["org_path"],
                level=org_node["level"],
                account_alias=account_alias,
                provider_id=self.provider.uuid,
            )
            if created:
                org_unit.created_timestamp = date
                org_unit.save()

    def _set_deleted_timestamp(self, date, accounts_list, orgs_list):
        """Updates the delete timestamp for values left in the yesterday lists."""
        with schema_context(self.schema):
            if self.yesterday_accounts != []:
                removed_accounts = AWSOrganizationalUnit.objects.filter(
                    account_alias__account_id__in=self.yesterday_accounts
                )
                for removed_account in removed_accounts:
                    removed_account.deleted_timestamp = date
                    removed_account.save()
                    LOG.info(f"Updating account={removed_account.account_alias} with delete_timestamp={date}")
            if self.yesterday_orgs != []:
                removed_org_units = AWSOrganizationalUnit.objects.filter(org_unit_id__in=self.yesterday_orgs)
                for removed_org_unit in removed_org_units:
                    removed_org_unit.deleted_timestamp = date
                    removed_org_unit.save()
                    LOG.info(f"Updating org={removed_org_unit.org_unit_id} with delete_timestamp={date}")

    def insert_tree(self, day_list):  # noqa: C901
        """Inserts the tree into the database."""
        try:
            for day_dict in day_list:
                day = day_dict["day"]
                date_delta = day["date"]
                date = self.calculate_date(date_delta)
                LOG.info(f"Converted date_delta={date_delta} to {date}")
                for node in day["nodes"]:
                    org_id = node["org_unit_id"]
                    parent_path = node.get("parent_path", "")
                    if parent_path == "":
                        node["org_path"] = org_id
                        node["level"] = 0
                    else:
                        node["level"] = parent_path.count("&") + 1
                        node["org_path"] = parent_path + "&" + org_id
                    if org_id in self.yesterday_orgs:
                        self.yesterday_orgs.remove(org_id)
                    self.today_orgs.append(org_id)
                    self._insert_org_sql(node, date)
                    if node.get("accounts"):
                        for account in node.get("accounts"):
                            account_id = account["account_alias_id"]
                            if account_id in self.yesterday_accounts:
                                self.yesterday_accounts.remove(account_id)
                            self.today_accounts.append(account_id)
                            self._insert_account(node, account, date)
                self._set_deleted_timestamp(date, self.yesterday_accounts, self.yesterday_orgs)
                self.yesterday_accounts = self.today_accounts
                self.yesterday_orgs = self.today_orgs
                self.today_accounts = []
                self.today_orgs = []
        except KeyError as e:
            err_msg = f"Error: Tree structure is not formatted correctly, could not find the following key: {e}"
            raise InsertAwsOrgTreeError(err_msg)
