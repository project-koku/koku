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

    def test_handle_missing_foreign_data(self):
        p = Provider.objects.first()
        p.customer = None
        p.billing_source = None
        p.authentication = None
        exc = None

        try:
            info = CURAccountsDB.get_account_information(p)
        except Exception as e:
            exc = e

        self.assertIsNone(exc)
        self.assertIsNone(info["schema_name"])
        self.assertIsNone(info["credentials"])
        self.assertIsNone(info["data_source"])
        self.assertIsNone(info["schema_name"])

    def test_get_accounts_from_source(self):
        """Test to get all accounts."""
        accounts = CURAccountsDB().get_accounts_from_source()
        expected_count = Provider.objects.count()
        self.assertEqual(len(accounts), expected_count)

        for account in accounts:
            if account.get("provider_type") in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                self.assertEqual(account.get("credentials"), self.aws_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.aws_provider.billing_source.data_source)
                self.assertEqual(account.get("schema_name"), self.schema_name)
            elif account.get("provider_type") == Provider.PROVIDER_OCP:
                self.assertIn(
                    account.get("credentials"),
                    [
                        self.ocp_provider.authentication.credentials,  # OCP-on-Prem
                        self.ocp_on_aws_ocp_provider.authentication.credentials,
                        self.ocp_on_azure_ocp_provider.authentication.credentials,
                        self.ocp_on_gcp_ocp_provider.authentication.credentials,
                    ],
                )
                self.assertTrue(
                    (account.get("data_source") == self.ocp_provider.billing_source.data_source)
                    or account.get("data_source") is None
                )
                self.assertEqual(account.get("schema_name"), self.schema_name)
            elif account.get("provider_type") in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                self.assertEqual(account.get("credentials"), self.azure_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.azure_provider.billing_source.data_source)
                self.assertEqual(account.get("schema_name"), self.schema_name)
            elif account.get("provider_type") in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                self.assertEqual(account.get("credentials"), self.gcp_provider.authentication.credentials)
                self.assertEqual(account.get("data_source"), self.gcp_provider.billing_source.data_source)
                self.assertEqual(account.get("schema_name"), self.schema_name)
            elif account.get("provider_type") in (Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL):
                self.assertEqual(account.get("data_source"), self.oci_provider.billing_source.data_source)
                self.assertEqual(account.get("schema_name"), self.schema_name)
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

    def test_get_accounts_with_active_and_paused(self):
        """Test to get accounts when either active or paused."""
        providers = Provider.objects.all()
        num_providers = len(providers)
        first = providers[0]

        table = [
            {"active": True, "paused": True, "expected": num_providers - 1},
            {"active": True, "paused": False, "expected": num_providers},
            {"active": False, "paused": True, "expected": num_providers - 1},
            {"active": False, "paused": False, "expected": num_providers - 1},
        ]
        for test in table:
            first.active = test["active"]
            first.paused = test["paused"]
            first.save()
            accounts = CURAccountsDB().get_accounts_from_source()
            self.assertEqual(len(accounts), test["expected"])

    def test_get_specific_account_with_active_and_paused(self):
        """Test to get accounts when either active or paused."""
        first = Provider.objects.first()

        table = [
            {"active": True, "paused": True, "expected": 0},
            {"active": True, "paused": False, "expected": 1},
            {"active": False, "paused": True, "expected": 0},
            {"active": False, "paused": False, "expected": 0},
        ]
        for test in table:
            first.active = test["active"]
            first.paused = test["paused"]
            first.save()
            accounts = CURAccountsDB().get_accounts_from_source(first.uuid)
            self.assertEqual(len(accounts), test["expected"])
