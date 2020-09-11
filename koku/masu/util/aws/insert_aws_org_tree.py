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
"""AWS Utility functions for inserting a aws org unit tree for testing."""
import logging
import os
import sys
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from datetime import timedelta

import yaml
from tenant_schemas.utils import schema_context

from reporting.provider.aws.models import AWSAccountAlias
from reporting.provider.aws.models import AWSOrganizationalUnit

# import psycopg2
# import requests
# from django.db import transaction
# from psycopg2 import sql

LOG = logging.getLogger(__name__)


class InsertAwsOrgTree(ABC):
    """Insert aws org tree abstract class."""

    def __init__(self, schema, start_date=None, tree_yaml=None):
        self.schema = schema
        self.start_date = start_date
        self.yesterday_accounts = []
        self.yesterday_orgs = []
        self.today_accounts = []
        self.today_orgs = []
        self.nise_accounts = []
        self.account_alias_mapping = {}
        self.tree_yaml = tree_yaml

    @abstractmethod
    def _insert_org_sql(self, org_node, date):
        """Inserts the org unit information into the database."""

    @abstractmethod
    def _insert_account(self, org_node, act_info, date):
        """Inserts the account information in the database."""

    @abstractmethod
    def _set_deleted_timestamp(self, date, accounts_list, orgs_list):
        """Updates the delete timestamp for values left in the yesterday lists."""

    def _load_yaml_file(self, filename):
        """Local data from yaml file."""
        yamlfile = None
        if not os.path.isfile(filename):
            LOG.error(f"Error: No such file: {filename}")
            sys.exit(1)
        try:
            with open(filename, "r+") as yaml_file:
                yamlfile = yaml.safe_load(yaml_file)
        except TypeError:
            yamlfile = yaml.safe_load(filename)
        return yamlfile

    def calculate_date(self, day_delta):
        """Calculate the date based off of a delta and a range start date."""
        if not self.start_date:
            today = datetime.today().date()
            self.start_date = today.replace(day=1)
        date = self.start_date + timedelta(days=day_delta)
        if isinstance(date, datetime):
            return str(date.date())
        return str(date)

    def insert_tree(self, day_list=None):  # noqa: C901
        """Inserts the tree into the database."""
        try:
            if self.tree_yaml:
                yaml_contents = self._load_yaml_file(self.tree_yaml)
                day_list = yaml_contents["account_structure"]["days"]
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
                            if account_id not in self.nise_accounts:
                                self.nise_accounts.append(account_id)
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
            LOG.error(
                f"Error: '{self.tree_yml_path}' file is not formatted correctly, could not find the following key: {e}"
            )
            sys.exit(1)


class InsertOrgTreeDjangoORM(InsertAwsOrgTree):
    """Insert the org tree using the django orm.

    This child class is used in the internal masu endpoint: crawl_account_hierarchy to insert
    org unit tree structure for CI/QA.
    """

    def __init__(self, schema, start_date=None, tree_yaml=None):
        """
        Object to crawl the org unit structure for accounts to org units.
        Args:
            schema (String): database
        """
        super().__init__(schema=schema, start_date=start_date, tree_yaml=tree_yaml)

    def _insert_org_sql(self, org_node, date):
        """Inserts the org unit information into the database."""
        with schema_context(self.schema):
            org_unit, created = AWSOrganizationalUnit.objects.get_or_create(
                org_unit_name=org_node["org_unit_name"],
                org_unit_id=org_node["org_unit_id"],
                org_unit_path=org_node["org_path"],
                level=org_node["level"],
                account_alias=None,
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


# class InsertAwsOrgTreeRawSql(InsertAwsOrgTree):
#     """Inserts tree using raw sql."""

#     def __init__(self, schema, db_name, start_date=None, tree_yaml=None):
#         """
#         Object to crawl the org unit structure for accounts to org units.
#         Args:
#             schema (String): database
#         """
#         super().__init__(schema=schema, start_date=start_date, tree_yaml=tree_yaml)
#         self.db_name = db_name
#         self.cursor = self._establish_db_conn()

#     def require_env(self, envvar):
#         """Require that the env var be set to move forward with script."""
#         var_value = os.getenv(envvar)
#         if var_value is None:
#             LOG.error(f"The variable '{envvar}' is required in your environment.")
#             sys.exit(1)
#         return var_value

#     def _establish_db_conn(self):
#         """Creates a connection to the database."""
#         dbinfo = {
#             "database": self.db_name,
#             "user": self.require_env("DATABASE_USER"),
#             "password": self.require_env("DATABASE_PASSWORD"),
#             "port": self.require_env("POSTGRES_SQL_SERVICE_PORT"),
#             "host": self.require_env("POSTGRES_SQL_SERVICE_HOST"),
#         }
#         with psycopg2.connect(**dbinfo) as conn:
#             conn.autocommit = True
#             cursor = conn.cursor()
#         return cursor

#     def _insert_account(self, org_node, act_info, date):
#         """Inserts the account information in the database."""
#         # Make sure the account alias is created and get id
#         account_alias_sql = """INSERT INTO {schema}.reporting_awsaccountalias (account_id, account_alias)
#                                VALUES (%s, %s) ON CONFLICT (account_id) DO NOTHING;
#                                SELECT id FROM {schema}.reporting_awsaccountalias WHERE account_id = %s;"""
#         account_alias_sql = sql.SQL(account_alias_sql).format(schema=sql.Identifier(self.schema))
#         values = [act_info["account_alias_id"], act_info["account_alias_name"], act_info["account_alias_id"]]
#         self.cursor.execute(account_alias_sql, values)
#         LOG.debug(f"Adding account '{values[1]}' to account alias table.")
#         account_alias_id = self.cursor.fetchone()[0]
#         select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
#                         WHERE org_unit_name = %s AND org_unit_id = %s AND org_unit_path = %s
#                         AND level = %s AND account_alias_id = %s"""
#         select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
#         values = [
#             org_node["org_unit_name"],
#             org_node["org_unit_id"],
#             org_node["org_path"],
#             org_node["level"],
#             account_alias_id,
#         ]
#         self.cursor.execute(select_sql, values)
#         org_exists = self.cursor.fetchone()
#         if org_exists is None:
#             insert_account_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
#                                     (org_unit_name, org_unit_id, org_unit_path, created_timestamp,
#                                     level, account_alias_id) VALUES (%s, %s, %s, %s, %s, %s)"""
#             insert_account_sql = sql.SQL(insert_account_sql).format(schema=sql.Identifier(self.schema))
#             values = [
#                 org_node["org_unit_name"],
#                 org_node["org_unit_id"],
#                 org_node["org_path"],
#                 date,
#                 org_node["level"],
#                 account_alias_id,
#             ]
#             self.account_alias_mapping[account_alias_id] = act_info
#             self.cursor.execute(insert_account_sql, values)
#             LOG.info(
#                 f"Adding account='{act_info['account_alias_name']}' "
#                 f"to org={org_node['org_unit_id']} on created_timestamp={date}."
#             )

#     def _insert_org_sql(self, org_node, date):
#         """Inserts the org unit information into the database."""
#         select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
#                         WHERE org_unit_name = %s and org_unit_id = %s and org_unit_path = %s and level = %s"""
#         select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
#         values = [org_node["org_unit_name"], org_node["org_unit_id"], org_node["org_path"], org_node["level"]]
#         self.cursor.execute(select_sql, values)
#         org_exists = self.cursor.fetchone()
#         if org_exists is None:
#             org_insert_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
#                                 (org_unit_name, org_unit_id, org_unit_path, created_timestamp, level)
#                                 VALUES (%s, %s, %s, %s, %s);"""
#             org_insert_sql = sql.SQL(org_insert_sql).format(schema=sql.Identifier(self.schema))
#             values = [
#                 org_node["org_unit_name"],
#                 org_node["org_unit_id"],
#                 org_node["org_path"],
#                 date,
#                 org_node["level"],
#             ]
#             self.cursor.execute(org_insert_sql, values)
#             LOG.info(
#                 f"Creating OU={org_node['org_unit_id']} with path={org_node['org_path']} "
#                 f"at level={org_node['level']} on created_timestamp={date}."
#             )

#     def _set_deleted_timestamp(self, date, accounts_list, orgs_list):
#         """Updates the delete timestamp for values left in the yesterday lists."""
#         if accounts_list != []:
#             for account_id in accounts_list:
#                 alias_query = """SELECT id FROM {schema}.reporting_awsaccountalias WHERE account_id = %s;"""
#                 alias_query = sql.SQL(alias_query).format(schema=sql.Identifier(self.schema))
#                 self.cursor.execute(alias_query, [account_id])
#                 alias_id = self.cursor.fetchone()[0]
#                 update_delete_sql = """UPDATE {schema}.reporting_awsorganizationalunit
#                                        SET deleted_timestamp = %s WHERE account_alias_id = %s"""
#                 update_delete_sql = sql.SQL(update_delete_sql).format(schema=sql.Identifier(self.schema))
#                 self.cursor.execute(update_delete_sql, [date, alias_id])
#                 act_info = self.account_alias_mapping.get(alias_id, {})
#                 LOG.info(f"Updating account={act_info.get('account_alias_name')} with delete_timestamp={date}")

#         if orgs_list != []:
#             for org_unit in orgs_list:
#                 update_delete_sql = """UPDATE {schema}.reporting_awsorganizationalunit
#                                        SET deleted_timestamp = %s WHERE org_unit_id = %s"""
#                 update_delete_sql = sql.SQL(update_delete_sql).format(schema=sql.Identifier(self.schema))
#                 self.cursor.execute(update_delete_sql, [date, org_unit])
#                 LOG.info(f"Updating org={org_unit} with delete_timestamp={date}")

# # KOKU TEST RUNNER
# # org_tree_obj = InsertAwsOrgTreeRawSql(schema=KokuTestRunner.schema,
#                 #                                         db_name=test_db_name,
#                 #                                         tree_yaml="scripts/aws_org_tree.yml",
#                 #                                         start_date=dates[0][0])
