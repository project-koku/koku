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
"""Test the AWSOrgUnitCrawler object."""
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from faker import Faker
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from reporting.provider.aws.models import AWSAccountAlias
from reporting.provider.aws.models import AWSOrganizationalUnit

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
BUCKET = FAKE.word()
P_UUID = FAKE.uuid4()
P_TYPE = Provider.PROVIDER_AWS
GEN_NUM_ACT_DEFAULT = 2


def _generate_act_for_parent_side_effect(parent_id, num_of_accounts=GEN_NUM_ACT_DEFAULT):
    """generates the account for parent side effect list"""
    side_effect_list = []
    for idx in range(num_of_accounts):
        act_dict = {
            "Accounts": [{"Id": f"{parent_id}-id-{idx}", "Name": f"{parent_id}-name-{idx}"}],
            "NextToken": f"{idx}",
        }
        if (idx + 1) == num_of_accounts:
            del act_dict["NextToken"]
        side_effect_list.append(act_dict)
    return side_effect_list


class AWSOrgUnitCrawlerTest(MasuTestCase):
    """Test Cases for the AWSOrgUnitCrawler object."""

    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.account = {
            "authentication": fake_arn(service="iam", generate_account_id=True),
            "customer_name": CUSTOMER_NAME,
            "billing_source": BUCKET,
            "provider_type": P_TYPE,
            "schema_name": self.schema,
            "provider_uuid": P_UUID,
        }

    def test_initializer(self):
        """Test AWSOrgUnitCrawler initializer."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        result_auth_cred = unit_crawler._auth_cred
        expected_auth_cred = self.account.get("authentication")
        self.assertEqual(result_auth_cred, expected_auth_cred)
        self.assertIsNone(unit_crawler.client)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_init_session(self, mock_session):
        """Test the method that retrieves of a aws client."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        mock_session.assert_called()

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_depaginate(self, mock_session):
        """Test the aws account info is depaginated"""
        mock_session.client = MagicMock()
        parent_id = "TestDepaginate"
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        side_effect_list = _generate_act_for_parent_side_effect(parent_id, 3)
        unit_crawler.client.list_accounts_for_parent.side_effect = side_effect_list
        accounts = unit_crawler._depaginate(
            function=unit_crawler.client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
        )
        self.assertIsNotNone(accounts)
        self.assertEqual(len(accounts), len(side_effect_list))
        for side_effect in side_effect_list:
            expected_account = side_effect["Accounts"][0]
            self.assertIn(expected_account, accounts)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_crawl_accounts_per_id(self, mock_session):
        """Test that the accounts are depaginated and saved to db."""
        mock_session.client = MagicMock()
        parent_id = "big_sub_org"
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        side_effect_list = _generate_act_for_parent_side_effect(parent_id, 3)
        unit_crawler.client.list_accounts_for_parent.side_effect = side_effect_list

        prefix = f"root&{parent_id}"
        ou = {"Id": parent_id, "Name": "Big Org Unit"}
        unit_crawler._crawl_accounts_per_id(ou, prefix)

        with schema_context(self.schema):
            node_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(node_count, len(side_effect_list))
            for side_effect in side_effect_list:
                act_id = side_effect["Accounts"][0]["Id"]
                acts_in_db = AWSOrganizationalUnit.objects.get(account_id=act_id)
                self.assertIsNotNone(acts_in_db)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_crawl_account_hierarchy(self, mock_session):
        """Test the crawling for account hierarchy."""
        mock_session.client = MagicMock()
        paginator_dict = {
            "r-0": {
                "OrganizationalUnits": [
                    {"Id": "ou-0", "Arn": "arn-0", "Name": "Big_Org_0"},
                    {"Id": "ou-1", "Arn": "arn-1", "Name": "Big_Org_1"},
                    {"Id": "ou-2", "Arn": "arn-2", "Name": "Big_Org_2"},
                ]
            },
            "ou-0": {"OrganizationalUnits": [{"Id": "sou-0", "Arn": "arn-0", "Name": "Sub_Org_0"}]},
            "ou-1": {"OrganizationalUnits": []},
            "ou-2": {"OrganizationalUnits": []},
            "sou-0": {"OrganizationalUnits": []},
        }
        account_side_effect = []
        paginator_side_effect = []
        ou_ids = ["r-0", "ou-0", "ou-1", "ou-2", "sou-0"]
        for ou_id in ou_ids:
            parent_acts = _generate_act_for_parent_side_effect(ou_id)
            account_side_effect.extend(parent_acts)
            paginator = MagicMock()
            paginator.paginate(ParentId=ou_id).build_full_result.return_value = paginator_dict[ou_id]
            paginator_side_effect.append(paginator)
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        unit_crawler.client.list_roots.return_value = {"Roots": [{"Id": "r-0", "Arn": "arn-0", "Name": "root_0"}]}
        unit_crawler.client.list_accounts_for_parent.side_effect = account_side_effect
        unit_crawler.client.get_paginator.side_effect = paginator_side_effect
        unit_crawler.crawl_account_hierarchy()
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            total_entries = (len(ou_ids) * GEN_NUM_ACT_DEFAULT) + len(ou_ids)
            self.assertEqual(cur_count, total_entries)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_crawl_org_for_acts(self, mock_session):
        "Test that if an exception is raised the crawl continues"
        mock_session.client = MagicMock()
        paginator_dict = {
            "r-0": {
                "OrganizationalUnits": [
                    {"Id": "ou-0", "Arn": "arn-0", "Name": "Big_Org_0"},
                    {"Id": "ou-1", "Arn": "arn-1", "Name": "Big_Org_1"},
                    {"Id": "ou-2", "Arn": "arn-2", "Name": "Big_Org_2"},
                ]
            },
            "ou-0": {"OrganizationalUnits": [{"Id": "sou-0", "Arn": "arn-0", "Name": "Sub_Org_0"}]},
            "ou-1": {"OrganizationalUnits": []},
            "ou-2": Exception("Error"),
            "sou-0": {"OrganizationalUnits": []},
        }
        account_side_effect = []
        paginator_side_effect = []
        ou_ids = ["r-0", "ou-0", "ou-1", "ou-2", "sou-0"]
        for ou_id in ou_ids:
            parent_acts = _generate_act_for_parent_side_effect(ou_id)
            account_side_effect.extend(parent_acts)
            paginator = MagicMock()
            paginator.paginate(ParentId=ou_id).build_full_result.return_value = paginator_dict[ou_id]
            paginator_side_effect.append(paginator)
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        unit_crawler.client.list_roots.return_value = {"Roots": [{"Id": "r-0", "Arn": "arn-0", "Name": "root_0"}]}
        unit_crawler.client.list_accounts_for_parent.side_effect = account_side_effect
        unit_crawler.client.get_paginator.side_effect = paginator_side_effect
        unit_crawler.crawl_account_hierarchy()
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            total_entries = (len(ou_ids) * GEN_NUM_ACT_DEFAULT) + len(ou_ids)
            self.assertEqual(cur_count, total_entries)

    def test_save_aws_org_method(self):
        """Test that saving to the database works."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 0)
        # Test that we are using a get or create so only one entry should be found.
        unit_crawler._save_aws_org_method("unit_name", "unit_id", "unit_path", "account_id")
        unit_crawler._save_aws_org_method("unit_name", "unit_id", "unit_path", "account_id")
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 1)
        # simulate an account being moved into a sub org
        unit_crawler._save_aws_org_method("unit_name", "unit_id", "unit_path&sub_org", "account_id")
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 2)
        # simulate a leaf node being added without an account_id
        unit_crawler._save_aws_org_method("unit_name2", "unit_id2", "unit_path2")
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 3)

    def test_build_accout_alias_map(self):
        """Test function that builds accout alias."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        with schema_context(self.schema):
            AWSAccountAlias.objects.create(account_id="12345", account_alias="kevan")
            AWSAccountAlias.objects.create(account_id="67890", account_alias="cody")
            # cur_count = AWSOrganizationalUnit.objects.count()
            # self.assertEqual(cur_count, 0)
            unit_crawler._build_accout_alias_map()
        print("#" * 120)
        print(unit_crawler.account_alias_map)

    def test_compute_org_structure_for_day(self):
        """Test function that computes org structure for a day."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._build_accout_alias_map()
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 0)

        # Add root node with 1 account
        created_nodes = []
        root = {"Id": "R_001", "Name": "root"}
        root_account = {"Id": "A_001", "Name": "Root Account"}
        created_nodes.append(unit_crawler._save_aws_org_method(root, "R_001", 0, None))
        created_nodes.append(unit_crawler._save_aws_org_method(root, "R_001", 0, root_account))

        # Add sub_org_unit_1 with 2 accounts
        sub_org_unit_1 = {"Id": "OU_1000", "Name": "sub_org_unit_1"}
        created_nodes.append(unit_crawler._save_aws_org_method(sub_org_unit_1, "R_001&OU_1000", 1, None))
        created_nodes.append(
            unit_crawler._save_aws_org_method(
                sub_org_unit_1, "R_001&OU_1000", 1, {"Id": "A_002", "Name": "Sub Org Account 2"}
            )
        )
        created_nodes.append(
            unit_crawler._save_aws_org_method(
                sub_org_unit_1, "R_001&OU_1000", 1, {"Id": "A_003", "Name": "Sub Org Account 3"}
            )
        )

        # Change created date to day_1
        with schema_context(self.schema):
            day_1 = (unit_crawler._date_accessor.today() - timedelta(2)).strftime("%Y-%m-%d")
            for node in created_nodes:
                node.created_timestamp = day_1
                node.save()
            curr_count = AWSOrganizationalUnit.objects.filter(created_timestamp__lte=day_1).count()
            self.assertEqual(curr_count, 5)

        # # Add sub_org_unit_2 and move sub_org_unit_1 2 accounts here
        created_nodes = []
        sub_org_unit_2 = {"Id": "OU_2000", "Name": "sub_org_unit_2"}
        created_nodes.append(unit_crawler._save_aws_org_method(sub_org_unit_2, "R_001&OU_2000", 1, None))
        created_nodes.append(
            unit_crawler._save_aws_org_method(
                sub_org_unit_2, "R_001&OU_2000", 1, {"Id": "A_002", "Name": "Sub Org Account 2"}
            )
        )
        created_nodes.append(
            unit_crawler._save_aws_org_method(
                sub_org_unit_2, "R_001&OU_2000", 1, {"Id": "A_003", "Name": "Sub Org Account 3"}
            )
        )
        deleted_nodes = unit_crawler._delete_aws_org_unit("OU_1000")

        # # Test fake node delete
        unit_crawler._delete_aws_org_unit("sub_org_unit_1_Fake")

        with schema_context(self.schema):
            day_2 = (unit_crawler._date_accessor.today() - timedelta(1)).strftime("%Y-%m-%d")
            for node in created_nodes:
                node.created_timestamp = day_2
                node.save()
            for node in deleted_nodes:
                node.deleted_timestamp = day_2
                node.save()
            curr_count = AWSOrganizationalUnit.objects.filter(created_timestamp__lte=day_2).count()
            self.assertEqual(curr_count, 8)

        unit_crawler._delete_aws_account("A_002")

        with schema_context(self.schema):
            curr_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(curr_count, 8)

        today = unit_crawler._date_accessor.today().strftime("%Y-%m-%d")
        unit_crawler._compute_org_structure_for_day(day_1)
        unit_crawler._compute_org_structure_for_day(day_2)
        unit_crawler._compute_org_structure_for_day(today)
        unit_crawler._compute_org_structure_for_day(day_1, today)
