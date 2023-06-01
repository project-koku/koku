#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSAccountAlias object."""
from unittest.mock import patch

from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias
from masu.test import MasuTestCase
from masu.util.aws.common import AwsArn


class AWSAccountAliasTest(MasuTestCase):
    """Test Cases for the AWSAccountAlias object."""

    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.account_id = "111111111111"
        role_arn = f"arn:aws:iam::{self.account_id}:role/CostManagement"
        self.credentials = {"role_arn": role_arn}
        self.arn = AwsArn(self.credentials)

    def test_initializer(self):
        """Test AWSAccountAlias initializer."""
        schema_name = "org1234567"
        accessor = AWSAccountAlias(self.credentials, schema_name)
        self.assertEqual(accessor._arn.arn, self.arn.arn)
        self.assertEqual(accessor._schema_name, schema_name)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization", return_value=[])
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_alias_no_alias(self, mock_get_alias, mock_get_account_names):
        """Test updating alias when none is set."""
        mock_get_alias.return_value = (self.account_id, None)
        accessor = AWSAccountAlias(self.credentials, "org1234567")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "org1234567")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertIsNone(db_access._obj.account_alias)

    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_names_by_organization", return_value=[])
    @patch("masu.external.accounts.labels.aws.aws_account_alias.get_account_alias_from_role_arn")
    def test_update_account_alias_with_alias(self, mock_get_alias, mock_get_account_names):
        """Test updating alias."""
        alias = "hccm-alias"
        mock_get_alias.return_value = (self.account_id, alias)
        accessor = AWSAccountAlias(self.credentials, "org1234567")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "org1234567")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        mock_get_alias.return_value = (self.account_id, None)
        accessor.update_account_alias()
        db_access = AccountAliasAccessor(self.account_id, "org1234567")
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
        accessor = AWSAccountAlias(self.credentials, "org1234567")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "org1234567")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        member_db_access = AccountAliasAccessor(member_account_id, "org1234567")
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
        accessor = AWSAccountAlias(self.credentials, "org1234567")
        accessor.update_account_alias()

        db_access = AccountAliasAccessor(self.account_id, "org1234567")
        self.assertEqual(db_access._obj.account_id, self.account_id)
        self.assertEqual(db_access._obj.account_alias, alias)

        member_db_access = AccountAliasAccessor(member_account_id, "org1234567")
        self.assertEqual(member_db_access._obj.account_id, member_account_id)
        self.assertEqual(member_db_access._obj.account_alias, member_account_id)
