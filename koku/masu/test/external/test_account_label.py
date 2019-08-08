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

"""Test the AccountLabel object."""

from unittest.mock import patch
from masu.external.account_label import AccountLabel
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias
from masu.test import MasuTestCase


class AccountLabelTest(MasuTestCase):
    """Test Cases for the AccountLabel object."""

    def test_initializer(self):
        """Test AccountLabel initializer."""
        accessor = AccountLabel('roleARN', 'acct10001', 'AWS')
        self.assertIsInstance(accessor.label, AWSAccountAlias)

    def test_initializer_not_supported_provider(self):
        """Test AccountLabel initializer for unsupported provider."""
        accessor = AccountLabel('roleARN', 'acct10001', 'unsupported')
        self.assertIsNone(accessor.label)

    def test_get_label_details(self):
        """Test getting label details for supported provider."""
        accessor = AccountLabel('roleARN', 'acct10001', 'AWS')
        mock_id = 333
        mock_alias = 'three'
        with patch.object(
            AWSAccountAlias, 'update_account_alias', return_value=(mock_id, mock_alias)
        ):
            account_id, alias = accessor.get_label_details()
            self.assertEqual(account_id, 333)
            self.assertEqual(alias, 'three')

    def test_get_label_details_unsupported(self):
        """Test getting label details for supported provider."""
        accessor = AccountLabel('roleARN', 'acct10001', 'unsupported')
        account_id, alias = accessor.get_label_details()
        self.assertIsNone(account_id)
        self.assertIsNone(alias)
