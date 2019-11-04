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
from unittest.mock import patch

from masu.external import AMAZON_WEB_SERVICES, AZURE, OPENSHIFT_CONTAINER_PLATFORM
from masu.external.accounts.db.cur_accounts_db import CURAccountsDB
from masu.test import MasuTestCase


class CURAccountsDBTest(MasuTestCase):
    """Test Cases for the CURAccountsDB object."""

    def test_get_accounts_from_source(self):
        """Test to get all accounts"""
        accounts = CURAccountsDB().get_accounts_from_source()
        if len(accounts) != 3:
            self.fail('unexpected number of accounts')

        for account in accounts:
            if account.get('provider_type') == AMAZON_WEB_SERVICES:
                self.assertEqual(account.get('authentication'), self.aws_provider_resource_name)
                self.assertEqual(account.get('billing_source'), self.aws_test_billing_source)
                self.assertEqual(account.get('customer_name'), self.schema)
            elif account.get('provider_type') == OPENSHIFT_CONTAINER_PLATFORM:
                self.assertEqual(account.get('authentication'), self.ocp_provider_resource_name)
                self.assertEqual(account.get('billing_source'), None)
                self.assertEqual(account.get('customer_name'), self.schema)
            elif account.get('provider_type') == AZURE:
                self.assertEqual(account.get('authentication'), self.azure_credentials)
                self.assertEqual(account.get('billing_source'), self.azure_data_source)
                self.assertEqual(account.get('customer_name'), self.schema)
            else:
                self.fail('Unexpected provider')

    def test_get_accounts_from_source_with_inactive(self):
        """Test to get all active accounts."""
        self.aws_provider.active = False
        self.aws_provider.save()

        accounts = CURAccountsDB().get_accounts_from_source()
        if len(accounts) != 2:
            self.fail('unexpected number of accounts')
