#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
            elif account.get("provider_type") in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                self.assertEqual(account.get("credentials"), self.gcp_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.gcp_provider.billing_source.data_source)
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
