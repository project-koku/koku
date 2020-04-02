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
# from unittest.mock import MagicMock
from unittest.mock import patch

from faker import Faker
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from reporting.provider.aws.models import AWSOrganizationalUnit

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
BUCKET = FAKE.word()
P_UUID = FAKE.uuid4()
P_TYPE = Provider.PROVIDER_AWS


def generate_accounts(self, ParentId):
    """
        TODO: FILL IN
        """
    gen_accounts_dict = {}
    last_nxt_tkn = ParentId
    for idx in range(self.act_num_max):
        new_nxt_tkn = f"nxt-{ParentId}-{idx}"
        gen_accounts_dict[last_nxt_tkn] = {
            "Accounts": [{"Id": f"{ParentId}-id-{idx}", "Name": f"{ParentId}-name-{idx}"}],
            "NextToken": new_nxt_tkn,
        }
        nxt_idx = idx + 1
        if nxt_idx == self.act_num_max:
            del gen_accounts_dict[last_nxt_tkn]["NextToken"]
        else:
            last_nxt_tkn = new_nxt_tkn
    self.accounts = gen_accounts_dict


class FakeClient:
    """
    Fake Boto Client object
    """

    def __init__(self):
        self.act_num_max = 3
        self.accounts = dict()
        self.account_expected_results = []

    def generate_accounts_for_parent(self, ParentId):
        """
        TODO: FILL IN
        """
        gen_accounts_dict = {}
        last_nxt_tkn = ParentId
        for idx in range(self.act_num_max):
            new_nxt_tkn = f"nxt-{ParentId}-{idx}"
            gen_accounts_dict[last_nxt_tkn] = {
                "Accounts": [{"Id": f"{ParentId}-id-{idx}", "Name": f"{ParentId}-name-{idx}"}],
                "NextToken": new_nxt_tkn,
            }
            nxt_idx = idx + 1
            if nxt_idx == self.act_num_max:
                del gen_accounts_dict[last_nxt_tkn]["NextToken"]
            else:
                last_nxt_tkn = new_nxt_tkn
        self.accounts = gen_accounts_dict

    def list_accounts_for_parent(self, ParentId, NextToken=None):
        """
        This method is to mock the aws list_accounts_for_parents call
        https://docs.aws.amazon.com/cli/latest/reference/organizations/list-accounts-for-parent.html
        """
        if NextToken:
            key = NextToken
        else:
            key = ParentId
            if not self.accounts.get(ParentId, None):
                self.generate_accounts_for_parent(ParentId)
        return self.accounts.get(key)


class FakeSession:
    """
    Fake Boto Session object.

    This is here because Moto doesn't mock out the 'cur' endpoint yet. As soon
    as Moto supports 'cur', this can be removed.
    """

    @staticmethod
    def client(service):
        """Return a fake AWS Client with a report."""
        return FakeClient()


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

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_session(self, mock_session):
        """Test the method that retrieves of a aws client."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler.get_session()
        mock_session.assert_called()

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_depaginate(self, mock_session):
        unit_crawler = AWSOrgUnitCrawler(self.account)
        unit_crawler.client = unit_crawler.get_session()
        parent_id = "TestDepaginate"
        accounts = unit_crawler.depaginate(
            function=unit_crawler.client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
        )
        self.assertIsNotNone(accounts)
        self.assertEqual(len(accounts), unit_crawler.client.act_num_max)
        for idx in range(unit_crawler.client.act_num_max):
            expected_account = {"Id": f"{parent_id}-id-{idx}", "Name": f"{parent_id}-name-{idx}"}
            self.assertIn(expected_account, accounts)

    # def test_depaginate_magic_mock(self):
    #     unit_crawler = AWSOrgUnitCrawler(self.account)
    #     parent_id = "TestDepaginate"
    #     unit_crawler.client = MagicMock(name='list_accounts_for_parent', side_effect=[{
    #             "Accounts": [{"Id": f"{parent_id}-id-1", "Name": f"{parent_id}-name-1"}],
    #             "NextToken": '1',
    #         },
    #         {
    #             "Accounts": [{"Id": f"{parent_id}-id-2", "Name": f"{parent_id}-name-2"}],
    #             "NextToken": '2',
    #         },
    #         {
    #             "Accounts": [{"Id": f"{parent_id}-id-3", "Name": f"{parent_id}-name-3"}],
    #             "NextToken": '3',
    #         }])
    #     accounts = unit_crawler.depaginate(
    #         function=unit_crawler.client.list_accounts_for_parent, resource_key="Accounts", ParentId=parent_id
    #     )
    #     self.assertIsNotNone(accounts)
    #     self.assertEqual(len(accounts), unit_crawler.client.act_num_max)
    #     for idx in range(unit_crawler.client.act_num_max):
    #         expected_account = {"Id": f"{parent_id}-id-{idx}", "Name": f"{parent_id}-name-{idx}"}
    #         self.assertIn(expected_account, accounts)

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
        # TODO: We need to check to make sure the timestamp was entered
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 2)
        # simulate a leaf node being added without an account_id
        unit_crawler._save_aws_org_method("unit_name2", "unit_id2", "unit_path2")
        with schema_context(self.schema):
            cur_count = AWSOrganizationalUnit.objects.count()
            self.assertEqual(cur_count, 3)
