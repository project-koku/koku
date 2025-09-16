#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Azure Client Class."""
import random
from unittest.mock import patch
from unittest.mock import PropertyMock

from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from django.test import TestCase
from faker import Faker

from providers.azure.client import AzureClientFactory

FAKE = Faker()


class AzureClientFactoryTestCase(TestCase):
    """Parent Class for AzureClientFactory test cases."""

    def setUp(self):
        """Test case setup."""
        self.clouds = ["china", "germany", "public", "usgov"]

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_constructor(self, mock_get_token):
        """Test that we can create an AzureClientFactory object."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj, AzureClientFactory))

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_costmanagement_client(self, mock_get_token):
        """Test the costmanagement_client property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj.cost_management_client, CostManagementClient))

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_credentials(self, mock_get_token):
        """Test the credentials property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj._credentials, ClientSecretCredential))

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_storage_client(self, mock_get_token):
        """Test the storage_client property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj.storage_client, StorageManagementClient))

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_subscription_id(self, mock_get_token):
        """Test the subscription_id property."""
        subscription_id = FAKE.uuid4()
        obj = AzureClientFactory(
            subscription_id=subscription_id,
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(obj.subscription_id, subscription_id)

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_cloud_storage_account(self, mock_get_token):
        """Test the cloud_storage_account method."""
        subscription_id = FAKE.uuid4()
        storage_account_name = FAKE.word()
        obj = AzureClientFactory(
            subscription_id=subscription_id,
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        with patch("providers.azure.client.AzureClientFactory.storage_client", new_callable=PropertyMock):
            cloud_account = obj.cloud_storage_account(storage_account_name)
            self.assertTrue(isinstance(cloud_account, BlobServiceClient))

    @patch("providers.azure.client.ClientSecretCredential.get_token")
    def test_scope_and_export_name(self, mock_get_token):
        """Test the scope and export_name properties."""
        subscription_id = FAKE.uuid4()
        scope = f"/subscriptions/{subscription_id}"
        export_name = "cost_export"
        obj = AzureClientFactory(
            subscription_id=subscription_id,
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
            scope=scope,
            export_name=export_name,
        )
        self.assertTrue(obj.scope, scope)
        self.assertTrue(obj.export_name, export_name)
