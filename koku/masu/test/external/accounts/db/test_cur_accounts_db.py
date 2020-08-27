#
# Copyright 2018 Red Hat, Inc.
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
"""Test the CURAccountsDB utility object."""
from api.models import Provider
from masu.external.accounts.db.cur_accounts_db import CURAccountsDB
from masu.test import MasuTestCase


class CURAccountsDBTest(MasuTestCase):
    """Test Cases for the CURAccountsDB object."""

    def test_get_accounts_from_source(self):
        """Test to get all accounts."""
        accounts = CURAccountsDB().get_accounts_from_source()
        expected_count = Provider.objects.count()
        self.assertEqual(len(accounts), expected_count)

        for account in accounts:
            if account.get("provider_type") in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                self.assertEqual(account.get("credentials"), self.aws_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.aws_provider.billing_source.data_source)
                self.assertEqual(account.get("customer_name"), self.schema)
            elif account.get("provider_type") == Provider.PROVIDER_OCP:
                self.assertIn(
                    account.get("credentials"),
                    [
                        self.ocp_on_aws_ocp_provider.authentication.credentials,
                        self.ocp_on_azure_ocp_provider.authentication.credentials,
                    ],
                )
                self.assertTrue(
                    (account.get("data_source") == self.ocp_provider.billing_source.data_source)
                    or account.get("data_source") is None
                )
                self.assertEqual(account.get("customer_name"), self.schema)
            elif account.get("provider_type") in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                self.assertEqual(account.get("credentials"), self.azure_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.azure_provider.billing_source.data_source)
                self.assertEqual(account.get("customer_name"), self.schema)
            else:
                self.fail("Unexpected provider")

    def test_get_accounts_from_source_with_inactive(self):
        """Test to get all active accounts."""
        self.aws_provider.active = False
        self.aws_provider.save()
        expected_count = Provider.objects.filter(active=True).count()

        accounts = CURAccountsDB().get_accounts_from_source()
        if len(accounts) != expected_count:
            self.fail("unexpected number of accounts")
