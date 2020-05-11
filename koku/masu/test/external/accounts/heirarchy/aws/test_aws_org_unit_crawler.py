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


def _generate_act_for_parent_side_effect(schema, parent_id, num_of_accounts=GEN_NUM_ACT_DEFAULT):
    """generates the account for parent side effect list, and saves result in AWSAccountAlias"""
    side_effect_list = []
    for idx in range(num_of_accounts):
        act_id = f"{parent_id}-id-{idx}"
        act_name = f"{parent_id}-name-{idx}"
        act_dict = {"Accounts": [{"Id": act_id, "Name": act_name}], "NextToken": f"{idx}"}
        if (idx + 1) == num_of_accounts:
            del act_dict["NextToken"]
        side_effect_list.append(act_dict)
        with schema_context(schema):
            AWSAccountAlias.objects.create(account_id=act_id, account_alias=act_name)
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
        with schema_context(self.schema):
            # Delete the rows created by the koku_test_runner. This next test suite
            # is intended to test how the crawler inserts the data into the database
            # which is easier to do without preloaded data.
            AWSOrganizationalUnit.objects.all().delete()

    def test_initializer(self):
        """Test AWSOrgUnitCrawler initializer."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        result_auth_cred = unit_crawler._auth_cred
        expected_auth_cred = self.account.get("authentication")
        self.assertEqual(result_auth_cred, expected_auth_cred)
        self.assertIsNone(unit_crawler._client)

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
        side_effect_list = _generate_act_for_parent_side_effect(self.schema, parent_id, 3)
        unit_crawler._build_accout_alias_map()
        unit_crawler._client.list_accounts_for_parent.side_effect = side_effect_list
        accounts = unit_crawler._depaginate_account_list(
            function=unit_crawler._client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
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
        side_effect_list = _generate_act_for_parent_side_effect(self.schema, parent_id, 3)
        unit_crawler._build_accout_alias_map()
        unit_crawler._client.list_accounts_for_parent.side_effect = side_effect_list
        unit_crawler._structure_yesterday = {}

        prefix = f"root&{parent_id}"
        ou = {"Id": parent_id, "Name": "Big Org Unit"}
        unit_crawler._crawl_accounts_per_id(ou, prefix, level=1)

        with schema_context(self.schema):
            acts_in_db = AWSOrganizationalUnit.objects.filter(account_alias__isnull=False)
            self.assertIsNotNone(acts_in_db)
            self.assertEqual(acts_in_db.count(), 3)

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
            parent_acts = _generate_act_for_parent_side_effect(self.schema, ou_id)
            account_side_effect.extend(parent_acts)
            paginator = MagicMock()
            paginator.paginate(ParentId=ou_id).build_full_result.return_value = paginator_dict[ou_id]
            paginator_side_effect.append(paginator)
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        unit_crawler._client.list_roots.return_value = {"Roots": [{"Id": "r-0", "Arn": "arn-0", "Name": "root_0"}]}
        unit_crawler._client.list_accounts_for_parent.side_effect = account_side_effect
        unit_crawler._client.get_paginator.side_effect = paginator_side_effect
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
            parent_acts = _generate_act_for_parent_side_effect(self.schema, ou_id)
            account_side_effect.extend(parent_acts)
            paginator = MagicMock()
            paginator.paginate(ParentId=ou_id).build_full_result.return_value = paginator_dict[ou_id]
            paginator_side_effect.append(paginator)
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._init_session()
        unit_crawler._client.list_roots.return_value = {"Roots": [{"Id": "r-0", "Arn": "arn-0", "Name": "root_0"}]}
        unit_crawler._client.list_accounts_for_parent.side_effect = account_side_effect
        unit_crawler._client.get_paginator.side_effect = paginator_side_effect
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
            AWSAccountAlias.objects.create(account_id="A_001", account_alias="Root Account")
        unit_crawler._build_accout_alias_map()
        unit_crawler._structure_yesterday = {}
        # Test that we are using a get or create so only one entry should be found.
        root_ou = {"Id": "R_001", "Name": "root"}
        root_account = {"Id": "A_001", "Name": "Root Account"}
        unit_crawler._save_aws_org_method(root_ou, "unit_path", 0, root_account)
        unit_crawler._save_aws_org_method(root_ou, "unit_path", 0, root_account)
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 1)
        # simulate an account being moved into a big org
        big_ou = {"Id": "R_001", "Name": "Big0"}
        unit_crawler._save_aws_org_method(big_ou, "unit_path&big_org", 1, root_account)
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 2)
        # simulate a leaf node being added without an account_id
        unit_crawler._save_aws_org_method(root_ou, "unit_path", 0)
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 3)

    def test_build_account_alias_map(self):
        """Test function that builds account alias map."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        with schema_context(self.schema):
            account_1 = AWSAccountAlias.objects.create(account_id="12345", account_alias="a1")
            account_2 = AWSAccountAlias.objects.create(account_id="67890", account_alias="a2")
            unit_crawler._build_accout_alias_map()
        self.assertIsNotNone(unit_crawler._account_alias_map)

        self.assertIn(account_1.account_id, unit_crawler._account_alias_map.keys())
        self.assertEqual(unit_crawler._account_alias_map.get(account_1.account_id), account_1)

        self.assertIn(account_2.account_id, unit_crawler._account_alias_map.keys())
        self.assertEqual(unit_crawler._account_alias_map.get(account_2.account_id), account_2)

    def test_compute_org_structure_interval(self):
        """Test function that computes org structure for an interval."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler._build_accout_alias_map()
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 0)
        unit_crawler._structure_yesterday = {}
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

        # Change created date to two_days_ago
        with schema_context(self.schema):
            two_days_ago = (unit_crawler._date_accessor.today() - timedelta(2)).strftime("%Y-%m-%d")
            for node in created_nodes:
                node.created_timestamp = two_days_ago
                node.save()
            curr_count = AWSOrganizationalUnit.objects.filter(created_timestamp__lte=two_days_ago).count()
            self.assertEqual(curr_count, 5)
            expected_count_2_days_ago = curr_count

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

        # Test fake node delete
        unit_crawler._delete_aws_org_unit("sub_org_unit_1_Fake")

        with schema_context(self.schema):
            yesterday = (unit_crawler._date_accessor.today() - timedelta(1)).strftime("%Y-%m-%d")
            for node in created_nodes:
                node.created_timestamp = yesterday
                node.save()
            for node in deleted_nodes:
                node.deleted_timestamp = yesterday
                node.save()
            curr_count = AWSOrganizationalUnit.objects.filter(created_timestamp__lte=yesterday).count()
            deleted_count = AWSOrganizationalUnit.objects.filter(deleted_timestamp__lte=yesterday).count()
            self.assertEqual(curr_count, 8)
            self.assertEqual(deleted_count, 3)
            expected_yesterday_count = curr_count - deleted_count

        unit_crawler._delete_aws_account("A_002")
        sub_org_unit_2 = {"Id": "OU_3000", "Name": "sub_org_unit_3"}
        unit_crawler._save_aws_org_method(sub_org_unit_2, "R_001&OU_3000", 1, None)

        with schema_context(self.schema):
            today = unit_crawler._date_accessor.today().strftime("%Y-%m-%d")
            curr_count = AWSOrganizationalUnit.objects.filter(created_timestamp__lte=today).count()
            deleted_count = AWSOrganizationalUnit.objects.filter(deleted_timestamp__lte=today).count()
            self.assertEqual(curr_count, 9)
            expected_today_count = curr_count - deleted_count

        # 2 days ago count matches
        structure_2_days_ago = unit_crawler._compute_org_structure_interval(two_days_ago)
        self.assertEqual(expected_count_2_days_ago, len(structure_2_days_ago))
        # Yesterday count matches
        unit_crawler._compute_org_structure_yesterday()
        self.assertEqual(expected_yesterday_count, len(unit_crawler._structure_yesterday))
        # today
        structure_today = unit_crawler._compute_org_structure_interval(today)
        self.assertEqual(len(structure_today), expected_today_count)
