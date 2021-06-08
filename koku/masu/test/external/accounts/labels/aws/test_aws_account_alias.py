#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSAccountAlias object."""
from unittest.mock import patch

from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias
from masu.test import MasuTestCase


class AWSAccountAliasTest(MasuTestCase):
    """Test Cases for the AWSAccountAlias object."""

    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.account_id = "111111111111"

    def test_initializer(self):
        """Test AWSAccountAlias initializer."""
        arn = "roleArn"
        schema = "acct10001"
        accessor = AWSAccountAlias(arn, schema)
        self.assertEqual(accessor._role_arn, arn)
        self.assertEqual(accessor._schema, schema)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization", return_value=[])
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_alias_no_alias(self, mock_get_alias, mock_get_account_names):
        """Test updating alias when none is set."""
        mock_get_alias.return_value = (self.account_id, None)
        role_arn = f"arn:aws:iam::{self.account_id}:role/CostManagement"
        accessor = AWSAccountAlias(role_arn, "acct10001")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "acct10001")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertIsNone(db_access._obj.account_alias)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization", return_value=[])
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_alias_with_alias(self, mock_get_alias, mock_get_account_names):
        """Test updating alias."""
        alias = "hccm-alias"
        mock_get_alias.return_value = (self.account_id, alias)
        role_arn = f"arn:aws:iam::{self.account_id}:role/CostManagement"
        accessor = AWSAccountAlias(role_arn, "acct10001")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "acct10001")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        mock_get_alias.return_value = (self.account_id, None)
        accessor.update_account_alias()
        db_access = AccountAliasAccessor(self.account_id, "acct10001")
        self.assertIsNone(db_access._obj.account_alias)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization")
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_via_orgs(self, mock_get_alias, mock_get_account_names):
        """Test update alias with org api response."""
        alias = "hccm-alias"
        mock_get_alias.return_value = (self.account_id, alias)
        member_account_id = "1234598760"
        member_account_name = "hccm-member"
        account_names = [
            {"id": self.account_id, "name": alias},
            {"id": member_account_id, "name": member_account_name},
        ]
        mock_get_account_names.return_value = account_names
        role_arn = f"arn:aws:iam::{self.account_id}:role/CostManagement"
        accessor = AWSAccountAlias(role_arn, "acct10001")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "acct10001")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        member_db_access = AccountAliasAccessor(member_account_id, "acct10001")
        self.assertEqual(member_db_access._obj.account_id, member_account_id)
        self.assertEqual(member_db_access._obj.account_alias, member_account_name)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization")
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_via_orgs_partial(self, mock_get_alias, mock_get_account_names):
        """Test update alias with org api with partial response."""
        alias = "hccm-alias"
        mock_get_alias.return_value = (self.account_id, alias)
        member_account_id = "1234596750"
        account_names = [{"id": self.account_id, "name": alias}, {"id": member_account_id}]
        mock_get_account_names.return_value = account_names
        role_arn = f"arn:aws:iam::{self.account_id}:role/CostManagement"
        accessor = AWSAccountAlias(role_arn, "acct10001")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "acct10001")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        member_db_access = AccountAliasAccessor(member_account_id, "acct10001")
        self.assertEqual(member_db_access._obj.account_id, member_account_id)
        self.assertEqual(member_db_access._obj.account_alias, member_account_id)
