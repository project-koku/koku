#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the CostUsageReportAccount object."""
from unittest.mock import patch

from api.models import Provider
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.test import MasuTestCase


class AccountsAccessorTest(MasuTestCase):
    """Test Cases for the AccountsAccessor object."""

    def test_get_accounts(self):
        """Test to get_access_credential."""
        account_objects = AccountsAccessor().get_accounts()
        expected_count = Provider.objects.count()

        self.assertEqual(len(account_objects), expected_count)

        for account in account_objects:
            with self.subTest(account=account):
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

    def test_get_aws_account_is_poll(self):
        """Test that the AWS account is returned given a provider uuid and it's a poll account."""
        account_objects = AccountsAccessor().get_accounts(self.aws_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        aws_account = account_objects.pop()
        self.assertIn(aws_account.get("provider_type"), (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL))
        self.assertTrue(AccountsAccessor().is_polling_account(aws_account))

    def test_get_ocp_account_is_not_poll(self):
        """Test that the OCP account is returned given a provider uuid and it's a listen account."""
        account_objects = AccountsAccessor().get_accounts(self.ocp_test_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        ocp_account = account_objects.pop()
        self.assertEqual(ocp_account.get("provider_type"), Provider.PROVIDER_OCP)
        self.assertFalse(AccountsAccessor().is_polling_account(ocp_account))

    @patch("masu.util.ocp.common.poll_ingest_override_for_provider", return_value=True)
    def test_get_ocp_override_account_is_poll(self, ocp_override):
        """Test that the OCP path returns OCP as a listen account."""
        account_objects = AccountsAccessor().get_accounts(self.ocp_test_provider_uuid)
        self.assertEqual(len(account_objects), 1)

        ocp_account = account_objects.pop()
        self.assertEqual(ocp_account.get("provider_type"), Provider.PROVIDER_OCP)
        self.assertTrue(AccountsAccessor().is_polling_account(ocp_account))

    def test_invalid_source_specification(self):
        """Test that error is thrown with invalid account source."""
        with self.assertRaises(AccountsAccessorError):
            AccountsAccessor("bad")
