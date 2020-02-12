#
# Copyright 2019 Red Hat, Inc.
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
"""Test the AzureService object."""
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

from azure.storage.blob import BlobClient
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import ContainerClient
from dateutil.relativedelta import relativedelta
from faker import Faker

from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.test import MasuTestCase
from providers.azure.client import AzureClientFactory

FAKE = Faker()


class AzureServiceTest(MasuTestCase):
    """Test Cases for the AzureService object."""

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.subscription_id = FAKE.uuid4()
        self.tenant_id = FAKE.uuid4()
        self.client_id = FAKE.uuid4()
        self.client_secret = FAKE.word()
        self.resource_group_name = FAKE.word()
        self.storage_account_name = FAKE.word()

        self.container_name = FAKE.word()
        self.current_date_time = datetime.today()
        self.export_directory = FAKE.word()

    def get_mock_client(self, blob_list=[], cost_exports=[]):
        """Generate an AzureService instance with mocked AzureClientFactory.

            Args:
                blob_list (list<Mock>) A list of Mock objects.

                        The blob_list Mock objects must have these attributes:

                            - name

                cost_exports (list<Mock>) A list of Mock objects.

                        The cost_exports Mock objects must have these
                        attributes:

                            - name
                            - delivery_info.destination.container
                            - delivery_info.destination.root_folder_path
                            - delivery_info.destination.resource_id

            Returns:
                (AzureService) An instance of AzureService with mocked AzureClientFactory
        """
        fake_data = FAKE.binary(length=1024 * 64)

        client = None
        with patch(
            "masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory
        ) as mock_factory:
            mock_factory.return_value = Mock(  # AzureClientFactory()
                spec=AzureClientFactory,
                cloud_storage_account=Mock(
                    return_value=Mock(  # .cloud_storage_account()
                        spec=BlobServiceClient,
                        get_blob_client=Mock(
                            return_value=Mock(  # .get_blob_client()
                                spec=BlobClient,
                                # .download_blob().readall()
                                download_blob=Mock(return_value=Mock(readall=Mock(return_value=fake_data))),
                            )
                        ),
                        get_container_client=Mock(
                            # .get_container_client().list_blobs()
                            return_value=Mock(spec=ContainerClient, list_blobs=Mock(return_value=blob_list))
                        ),
                    )
                ),
                # .cost_management_client.exports.list().value
                cost_management_client=Mock(exports=Mock(list=Mock(return_value=Mock(value=cost_exports)))),
                # .subscription_id
                subscription_id=self.subscription_id,
            )
            client = AzureService(
                self.subscription_id,
                self.tenant_id,
                self.client_id,
                self.client_secret,
                self.resource_group_name,
                self.storage_account_name,
            )
        return client

    def test_initializer(self):
        """Test the AzureService initializer."""
        svc = self.get_mock_client()
        self.assertIsInstance(svc, AzureService)

    def test_get_cost_export_for_key(self):
        """Test that a cost export is retrieved by a key."""
        today = self.current_date_time
        yesterday = today - relativedelta(days=1)
        test_matrix = [
            {"key": "{}_{}_day_{}".format(self.container_name, "blob", today.day), "expected_date": today.date()},
            {
                "key": "{}_{}_day_{}".format(self.container_name, "blob", yesterday.day),
                "expected_date": yesterday.date(),
            },
        ]

        for test in test_matrix:
            key = test.get("key")
            expected_modified_date = test.get("expected_date")

            mock_blob = Mock(properties=Mock(last_modified=Mock(date=Mock(return_value=expected_modified_date))))
            name_attr = PropertyMock(return_value=key)
            type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

            svc = self.get_mock_client(blob_list=[mock_blob])
            cost_export = svc.get_cost_export_for_key(key, self.container_name)
            self.assertIsNotNone(cost_export)
            self.assertEquals(cost_export.name, key)
            self.assertEquals(cost_export.properties.last_modified.date(), expected_modified_date)

    def test_get_cost_export_for_missing_key(self):
        """Test that a cost export is not retrieved by an incorrect key."""
        key = "{}_{}_wrong".format(self.container_name, "blob")

        mock_blob = Mock()
        name_attr = PropertyMock(return_value=FAKE.word())
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_cost_export_for_key(key, self.container_name)

    def test_get_latest_cost_export_for_path(self):
        """Test that the latest cost export is returned for a given path."""
        report_path = "{}_{}".format(self.container_name, "blob")

        mock_blob = Mock(properties=Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date()))))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        cost_export = svc.get_latest_cost_export_for_path(report_path, self.container_name)
        self.assertEquals(cost_export.properties.last_modified.date(), self.current_date_time.date())

    def test_get_latest_cost_export_for_path_missing(self):
        """Test that the no cost export is returned for a missing path."""
        report_path = FAKE.word()
        svc = self.get_mock_client()
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_latest_cost_export_for_path(report_path, self.container_name)

    def test_describe_cost_management_exports(self):
        """Test that cost management exports are returned for the account."""
        resource_id = (
            f"/subscriptions/{self.subscription_id}/resourceGroups/"
            f"{self.resource_group_name}/providers/Microsoft.Storage/"
            f"storageAccounts/{self.storage_account_name}"
        )

        mock_export = Mock(
            delivery_info=Mock(
                destination=Mock(
                    container=self.container_name, root_folder_path=self.export_directory, resource_id=resource_id
                )
            )
        )

        name_attr = PropertyMock(return_value=f"{self.container_name}_blob")
        type(mock_export).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(cost_exports=[mock_export])
        exports = svc.describe_cost_management_exports()

        self.assertEquals(len(exports), 1)
        for export in exports:
            self.assertEquals(export.get("container"), self.container_name)
            self.assertEquals(export.get("directory"), self.export_directory)
            self.assertIn("{}_{}".format(self.container_name, "blob"), export.get("name"))

    def test_describe_cost_management_exports_wrong_account(self):
        """Test that cost management exports are not returned from incorrect account."""
        resource_id = (
            f"/subscriptions/{FAKE.uuid4()}/resourceGroups/"
            f"{self.resource_group_name}/providers/Microsoft.Storage/"
            f"storageAccounts/{self.storage_account_name}"
        )

        mock_export = Mock(
            delivery_info=Mock(
                destination=Mock(
                    container=self.container_name, root_folder_path=self.export_directory, resource_id=resource_id
                )
            )
        )

        name_attr = PropertyMock(return_value=f"{self.container_name}_blob")
        type(mock_export).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(cost_exports=[mock_export])
        exports = svc.describe_cost_management_exports()
        self.assertEquals(exports, [])

    def test_download_cost_export(self):
        """Test that cost management exports are downloaded."""
        key = "{}_{}_day_{}".format(self.container_name, "blob", self.current_date_time.day)

        mock_blob = Mock()
        name_attr = PropertyMock(return_value=key)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        client = self.get_mock_client(blob_list=[mock_blob])
        file_path = client.download_cost_export(key, self.container_name)
        self.assertTrue(file_path.endswith(".csv"))
