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

"""Test the AccountAliasAccessor utility object."""

from masu.database.account_alias_accessor import AccountAliasAccessor
from tests import MasuTestCase


class AccountAliasAccessorTest(MasuTestCase):
    """Test Cases for the AuthDBAccessor object."""
    def setUp(self):
        """Setup test cases."""
        self.account_id = '123456789'
        self.schema = 'acct10001'
        self.accessor = AccountAliasAccessor(self.account_id, self.schema)
        self.accessor.commit()

    def tearDown(self):
        """Tear down test case."""
        self.accessor._session.delete(self.accessor._obj)
        self.accessor.commit()
        self.accessor.close_session()

    def test_initializer(self):
        """Test Initializer."""
        self.assertIsNotNone(self.accessor._session)
        self.assertTrue(self.accessor.does_db_entry_exist())

        obj = self.accessor._get_db_obj_query().first()
        self.assertEqual(obj.account_id, self.account_id)
        self.assertEqual(obj.account_alias, self.account_id)

    def test_set_account_alias(self):
        """test alias setter."""
        alias_name = 'test-alias'
        self.accessor.set_account_alias(alias_name)
        self.accessor.commit()
        obj = self.accessor._get_db_obj_query().first()
        self.assertEqual(obj.account_id, self.account_id)
        self.assertEqual(obj.account_alias, alias_name)
