#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Azure Client Class."""
import logging
import random
from unittest.mock import patch

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from django.test import TestCase
from faker import Faker

from providers.azure.client import AzureClientFactory

FAKE = Faker()
LOG = logging.getLogger(__name__)


class AzureClientFactoryTestCase(TestCase):
    """Parent Class for AzureClientFactory test cases."""

    def setUp(self):
        """Test case setup."""
        self.clouds = ["china", "germany", "public", "usgov"]

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_constructor(self, _):
        """Test that we can create an AzureClientFactory object."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj, AzureClientFactory))

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_costmanagement_client(self, _):
        """Test the costmanagement_client property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj.cost_management_client, CostManagementClient))

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_credentials(self, _):
        """Test the credentials property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj._credentials, ServicePrincipalCredentials))

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_resource_client(self, _):
        """Test the resource_client property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj.resource_client, ResourceManagementClient))

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_storage_client(self, _):
        """Test the storage_client property."""
        obj = AzureClientFactory(
            subscription_id=FAKE.uuid4(),
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        self.assertTrue(isinstance(obj.storage_client, StorageManagementClient))

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_subscription_id(self, _):
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

    @patch("providers.azure.client.ServicePrincipalCredentials.set_token")
    def test_cloud_storage_account(self, _):
        """Test the cloud_storage_account method."""
        subscription_id = FAKE.uuid4()
        resource_group_name = FAKE.word()
        storage_account_name = FAKE.word()
        obj = AzureClientFactory(
            subscription_id=subscription_id,
            tenant_id=FAKE.uuid4(),
            client_id=FAKE.uuid4(),
            client_secret=FAKE.word(),
            cloud=random.choice(self.clouds),
        )
        with patch.object(StorageManagementClient, "storage_accounts", return_value=None):
            cloud_account = obj.cloud_storage_account(resource_group_name, storage_account_name)
            self.assertTrue(isinstance(cloud_account, BlobServiceClient))
