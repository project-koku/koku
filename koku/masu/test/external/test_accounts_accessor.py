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

"""Test the CostUsageReportAccount object."""

from unittest.mock import patch
from masu.exceptions import CURAccountsInterfaceError
from masu.external import AMAZON_WEB_SERVICES, OPENSHIFT_CONTAINER_PLATFORM
from masu.external.accounts_accessor import AccountsAccessor, AccountsAccessorError
from masu.external.accounts.network.cur_accounts_network import CURAccountsNetwork
from tests import MasuTestCase


class AccountsAccessorTest(MasuTestCase):
    """Test Cases for the AccountsAccessor object."""

    def test_get_accounts(self):
        """Test to get_access_credential"""
        account_objects = AccountsAccessor().get_accounts()

        if len(account_objects) != 2:
            self.fail('unexpected number of accounts')

        for account in account_objects:
            if account.get('provider_type') == AMAZON_WEB_SERVICES:
                self.assertEqual(
                    account.get('authentication'), self.aws_provider_resource_name
                )
                self.assertEqual(
                    account.get('billing_source'), self.aws_test_billing_source
                )
                self.assertEqual(account.get('customer_name'), self.test_schema)
            elif account.get('provider_type') == OPENSHIFT_CONTAINER_PLATFORM:
                self.assertEqual(
                    account.get('authentication'), self.ocp_provider_resource_name
                )
                self.assertEqual(
                    account.get('billing_source'), self.ocp_test_billing_source
                )
                self.assertEqual(account.get('customer_name'), self.test_schema)
            else:
                self.fail('Unexpected provider')

    def test_get_aws_account_is_poll(self):
        """Test that the AWS account is returned given a provider uuid and it's a poll account."""
        account_objects = AccountsAccessor().get_accounts(self.aws_test_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        aws_account = account_objects.pop()
        self.assertEqual(aws_account.get('provider_type'), AMAZON_WEB_SERVICES)
        self.assertTrue(AccountsAccessor().is_polling_account(aws_account))

    def test_get_ocp_account_is_not_poll(self):
        """Test that the OCP account is returned given a provider uuid and it's a listen account."""
        account_objects = AccountsAccessor().get_accounts(self.ocp_test_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        ocp_account = account_objects.pop()
        self.assertEqual(ocp_account.get('provider_type'), OPENSHIFT_CONTAINER_PLATFORM)
        self.assertFalse(AccountsAccessor().is_polling_account(ocp_account))

    @patch('masu.util.ocp.common.poll_ingest_override_for_provider', return_value=True)
    def test_get_ocp_override_account_is_poll(self, ocp_override):
        """Test that the OCP-local path returns OCP as a listen account."""
        account_objects = AccountsAccessor().get_accounts(self.ocp_test_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        ocp_account = account_objects.pop()
        self.assertEqual(ocp_account.get('provider_type'), OPENSHIFT_CONTAINER_PLATFORM)
        self.assertTrue(AccountsAccessor().is_polling_account(ocp_account))

    def test_invalid_source_specification(self):
        """Test that error is thrown with invalid account source."""

        with self.assertRaises(AccountsAccessorError):
            AccountsAccessor('bad')

    def test_get_accounts_exception(self):
        """Test to get accounts with an exception."""
        with patch.object(
            CURAccountsNetwork,
            'get_accounts_from_source',
            side_effect=CURAccountsInterfaceError('test'),
        ):
            with self.assertRaises(AccountsAccessorError):
                AccountsAccessor('network').get_accounts()
