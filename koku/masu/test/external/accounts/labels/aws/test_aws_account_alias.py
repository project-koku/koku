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

"""Test the AWSAccountAlias object."""

import boto3
from unittest.mock import patch
from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias
from tests import MasuTestCase


class AWSAccountAliasTest(MasuTestCase):
    """Test Cases for the AWSAccountAlias object."""

    def setUp(self):
        """Setup test case."""
        self.account_id = '111111111111'

    def tearDown(self):
        """Teardown test case."""
        db_access = AccountAliasAccessor(self.account_id, 'acct10001')
        db_access._get_db_obj_query().delete()
        db_access.get_session().commit()
        db_access.close_session()

    def test_initializer(self):
        """Test AWSAccountAlias initializer."""
        arn = 'roleArn'
        schema = 'acct10001'
        accessor = AWSAccountAlias(arn, schema)
        self.assertEqual(accessor._role_arn, arn)
        self.assertEqual(accessor._schema, schema)

    @patch(
        'masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn'
    )
    def test_update_account_alias_no_alias(self, mock_get_alias):
        """Test updating alias when none is set."""
        mock_get_alias.return_value = (self.account_id, None)
        role_arn = 'arn:aws:iam::{}:role/CostManagement'.format(self.account_id)
        accessor = AWSAccountAlias(role_arn, 'acct10001')
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, 'acct10001')
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertIsNone(db_access._obj.account_alias)

    @patch(
        'masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn'
    )
    def test_update_account_alias_with_alias(self, mock_get_alias):
        """Test updating alias."""
        alias = 'hccm-alias'
        mock_get_alias.return_value = (self.account_id, alias)
        role_arn = 'arn:aws:iam::{}:role/CostManagement'.format(self.account_id)
        accessor = AWSAccountAlias(role_arn, 'acct10001')
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, 'acct10001')
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        mock_get_alias.return_value = (self.account_id, None)
        accessor.update_account_alias()
        db_access = AccountAliasAccessor(self.account_id, 'acct10001')
        self.assertIsNone(db_access._obj.account_alias)
