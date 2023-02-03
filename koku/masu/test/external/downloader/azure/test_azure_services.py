#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureService object."""
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

from adal.adal_error import AdalError
from azure.common import AzureException
from azure.core.exceptions import HttpResponseError
from azure.storage.blob import BlobClient
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import ContainerClient
from dateutil.relativedelta import relativedelta
from faker import Faker

from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.azure.azure_service import AzureServiceError
from masu.test import MasuTestCase
from providers.azure.client import AzureClientFactory

FAKE = Faker()


def throw_azure_exception(scope, extra=None):
    """Raises azure exception."""
    raise AzureException()


def throw_azure_http_error(scope):
    """Raises azure http error."""
    raise HttpResponseError()


def throw_azure_http_error_403(scope):
    """Raises azure http error."""
    error = HttpResponseError()
    error.status_code = 403
    raise error


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

    def get_mock_client(self, blob_list=[], cost_exports=[], scope=None, export_name=None):
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
        cost_export = None
        if len(cost_exports):
            cost_export = cost_exports[0]
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
                cost_management_client=Mock(
                    exports=Mock(
                        list=Mock(return_value=Mock(value=cost_exports)),
                        # .cost_management_client.exports.get().value
                        get=Mock(return_value=Mock(value=cost_export)),
                    )
                ),
                # .cost_management_client.exports.get().value
                # .subscription_id
                subscription_id=self.subscription_id,
                scope=scope,
                export_name=export_name,
            )
            client = AzureService(
                self.tenant_id,
                self.client_id,
                self.client_secret,
                self.resource_group_name,
                self.storage_account_name,
                self.subscription_id,
            )
        return client

    def test_initializer(self):
        """Test the AzureService initializer."""
        svc = self.get_mock_client()
        self.assertIsInstance(svc, AzureService)

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    def test_init_no_subscription_id(self, mock_factory):
        """Test that exception is raized with no subscription id provided."""

        class MockAzureFactory:
            subscription_id = None

        factory = MockAzureFactory()
        mock_factory.return_value = factory
        with self.assertRaises(AzureServiceError):
            AzureService(
                self.tenant_id, self.client_id, self.client_secret, self.resource_group_name, self.storage_account_name
            )

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

            mock_blob = Mock(last_modified=Mock(date=Mock(return_value=expected_modified_date)))
            name_attr = PropertyMock(return_value=key)
            type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

            svc = self.get_mock_client(blob_list=[mock_blob])
            cost_export = svc.get_cost_export_for_key(key, self.container_name)
            self.assertIsNotNone(cost_export)
            self.assertEqual(cost_export.name, key)
            self.assertEqual(cost_export.last_modified.date(), expected_modified_date)

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

        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date())))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        cost_export = svc.get_latest_cost_export_for_path(report_path, self.container_name)
        self.assertEqual(cost_export.last_modified.date(), self.current_date_time.date())

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

        self.assertEqual(len(exports), 1)
        for export in exports:
            self.assertEqual(export.get("container"), self.container_name)
            self.assertEqual(export.get("directory"), self.export_directory)
            self.assertIn("{}_{}".format(self.container_name, "blob"), export.get("name"))

    def test_get_latest_cost_export_http_error(self):
        """Test that the latest cost export catches the error for Azure HttpError."""
        report_path = "{}_{}".format(self.container_name, "blob")

        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date())))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        svc._cloud_storage_account.get_container_client.side_effect = throw_azure_http_error
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_latest_cost_export_for_path(report_path, self.container_name)

    def test_get_latest_cost_export_http_error_403(self):
        """Test that the latest cost export catches the error for Azure HttpError 403."""
        report_path = "{}_{}".format(self.container_name, "blob")

        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date())))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        svc._cloud_storage_account.get_container_client.side_effect = throw_azure_http_error_403
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_latest_cost_export_for_path(report_path, self.container_name)

    def test_get_latest_cost_export_no_container(self):
        """Test that the latest cost export catches the error for no container."""
        report_path = "blob"
        container_name = None

        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date())))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_latest_cost_export_for_path(report_path, container_name)

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
        self.assertEqual(exports, [])

    def test_describe_cost_management_exports_no_auth(self):
        """Test that cost management exports are not returned from incorrect account."""
        svc = self.get_mock_client(cost_exports=[Mock()])
        svc._factory.cost_management_client.exports.list.side_effect = throw_azure_exception
        with self.assertRaises(AzureCostReportNotFound):
            svc.describe_cost_management_exports()

    def test_download_cost_export(self):
        """Test that cost management exports are downloaded."""
        key = "{}_{}_day_{}".format(self.container_name, "blob", self.current_date_time.day)

        mock_blob = Mock()
        name_attr = PropertyMock(return_value=key)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        client = self.get_mock_client(blob_list=[mock_blob])
        file_path = client.download_cost_export(key, self.container_name)
        self.assertTrue(file_path.endswith(".csv"))

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory)
    def test_get_cost_export_for_key_exception(self, mock_factory):
        """Test that function handles a raised exception."""
        mock_factory.return_value = Mock(
            spec=AzureClientFactory,
            cloud_storage_account=Mock(
                return_value=Mock(
                    spec=BlobServiceClient,
                    get_container_client=Mock(
                        return_value=Mock(spec=ContainerClient, list_blobs=Mock(side_effect=AdalError("test error")))
                    ),
                )
            ),
        )
        with self.assertRaises(AzureServiceError):
            service = AzureService(
                self.tenant_id, self.client_id, self.client_secret, self.resource_group_name, self.storage_account_name
            )
            service.get_cost_export_for_key(key=FAKE.word(), container_name=FAKE.word())

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory)
    def test_download_cost_report_exception(self, mock_factory):
        """Test that function handles a raised exception."""
        key = FAKE.word()
        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=datetime.now())))
        name_attr = PropertyMock(return_value=key)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        mock_factory.return_value = Mock(
            spec=AzureClientFactory,
            cloud_storage_account=Mock(
                return_value=Mock(
                    spec=BlobServiceClient,
                    get_blob_client=Mock(side_effect=AdalError("test error")),
                    get_container_client=Mock(
                        return_value=Mock(spec=ContainerClient, list_blobs=Mock(return_value=[mock_blob]))
                    ),
                )
            ),
        )
        with self.assertRaises(AzureServiceError):
            service = AzureService(
                self.tenant_id, self.client_id, self.client_secret, self.resource_group_name, self.storage_account_name
            )
            service.download_cost_export(key=key, container_name=FAKE.word())

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory)
    def test_get_latest_cost_export_for_path_exception(self, mock_factory):
        """Test that function handles a raised exception."""
        mock_factory.return_value = Mock(
            spec=AzureClientFactory,
            cloud_storage_account=Mock(
                return_value=Mock(
                    spec=BlobServiceClient,
                    get_container_client=Mock(
                        return_value=Mock(spec=ContainerClient, list_blobs=Mock(side_effect=AdalError("test error")))
                    ),
                )
            ),
        )
        with self.assertRaises(AzureServiceError):
            service = AzureService(
                self.tenant_id, self.client_id, self.client_secret, self.resource_group_name, self.storage_account_name
            )
            service.get_latest_cost_export_for_path(report_path=FAKE.word(), container_name=FAKE.word())

    def test_describe_cost_management_exports_with_scope_and_name(self):
        """Test that cost management exports using scope and name are returned for the account."""
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

        scope = f"/subscriptions/{self.subscription_id}"
        svc = self.get_mock_client(cost_exports=[mock_export], scope=scope, export_name="cost_export")
        exports = svc.describe_cost_management_exports()

        self.assertEqual(len(exports), 1)

    def test_describe_cost_management_exports_with_scope_and_name_no_auth(self):
        """Test that cost management exports using scope and name are not returned from incorrect account."""
        scope = f"/subscriptions/{self.subscription_id}"
        svc = self.get_mock_client(cost_exports=[Mock()], scope=scope, export_name="cost_export")
        svc._factory.cost_management_client.exports.get.side_effect = throw_azure_exception
        with self.assertRaises(AzureCostReportNotFound):
            svc.describe_cost_management_exports()
