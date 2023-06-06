#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AccountLabel object."""
from unittest.mock import patch

from masu.external.account_label import AccountLabel
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


class AccountLabelTest(MasuTestCase):
    """Test Cases for the AccountLabel object."""

    def test_initializer(self):
        """Test AccountLabel initializer."""
        auth = {"role_arn": fake_arn()}
        accessor = AccountLabel(auth, "org1234567", "AWS")
        self.assertIsInstance(accessor.label, AWSAccountAlias)

    def test_initializer_not_supported_provider(self):
        """Test AccountLabel initializer for unsupported provider."""
        auth = {"role_arn": fake_arn()}
        accessor = AccountLabel(auth, "org1234567", "unsupported")
        self.assertIsNone(accessor.label)

    def test_get_label_details(self):
        """Test getting label details for supported provider."""
        auth = {"role_arn": fake_arn()}
        accessor = AccountLabel(auth, "org1234567", "AWS")
        mock_id = 333
        mock_alias = "three"
        with patch.object(AWSAccountAlias, "update_account_alias", return_value=(mock_id, mock_alias)):
            account_id, alias = accessor.get_label_details()
            self.assertEqual(account_id, 333)
            self.assertEqual(alias, "three")

    def test_get_label_details_unsupported(self):
        """Test getting label details for supported provider."""
        auth = {"role_arn": fake_arn()}
        accessor = AccountLabel(auth, "org1234567", "unsupported")
        account_id, alias = accessor.get_label_details()
        self.assertIsNone(account_id)
        self.assertIsNone(alias)
