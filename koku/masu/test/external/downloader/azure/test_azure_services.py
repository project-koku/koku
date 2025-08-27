#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureService object."""
from datetime import datetime
from tempfile import NamedTemporaryFile
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

from azure.common import AzureException
from azure.core.exceptions import AzureError
from azure.core.exceptions import ClientAuthenticationError
from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import ServiceRequestError
from azure.storage.blob import BlobClient
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import ContainerClient
from dateutil.relativedelta import relativedelta
from faker import Faker

from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.azure.azure_service import AzureServiceError
from masu.external.downloader.azure.azure_service import ResourceNotFoundError
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


class FakeBlob:
    def __init__(self, name, last_modified=None):
        self.name = name
        self.last_modified = last_modified


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

    def test_get_file_for_key(self):
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
            cost_export = svc.get_file_for_key(key, self.container_name)
            self.assertIsNotNone(cost_export)
            self.assertEqual(cost_export.name, key)
            self.assertEqual(cost_export.last_modified.date(), expected_modified_date)

    def test_get_file_for_missing_key(self):
        """Test that a cost export is not retrieved by an incorrect key."""
        key = "{}_{}_wrong".format(self.container_name, "blob")

        mock_blob = Mock()
        name_attr = PropertyMock(return_value=FAKE.word())
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_file_for_key(key, self.container_name)

    def test_get_latest_cost_export_for_path(self):
        """Test that the latest cost export is returned for a given path."""
        report_path = "{}_{}".format(self.container_name, "blob.csv.gz")

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

    def test_get_latest_manifest_for_path(self):
        """Given a list of blobs with multiple manifests, ensure the latest one is returned"""

        report_path = "/container/report/path"
        blobs = (
            FakeBlob(f"{report_path}/02/file01.csv", datetime(2022, 11, 2, 10, 20)),
            FakeBlob(f"{report_path}/02/_manifest.json", datetime(2022, 11, 2, 10, 23)),  # Latest manifest
            FakeBlob(f"{report_path}/01/file01.csv", datetime(2022, 11, 1, 10, 20)),
            FakeBlob(f"{report_path}/01/_manifest.json", datetime(2022, 11, 1, 10, 23)),
            FakeBlob(f"{report_path}/03/_manifest.json", datetime(2022, 10, 31)),
        )
        azure_service = self.get_mock_client(blob_list=blobs)
        latet_manifest = azure_service.get_latest_manifest_for_path(report_path, "some_container")

        self.assertEqual(latet_manifest.name, f"{report_path}/02/_manifest.json")

    def test_list_blobs_none(self):
        azure_service = self.get_mock_client()
        with self.assertRaisesRegex(AzureCostReportNotFound, "Unable to find files in container"):
            azure_service._list_blobs("", "")

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

    def test_download_file(self):
        """Test that cost management exports are downloaded."""
        key = "{}_{}_day_{}".format(self.container_name, "blob", self.current_date_time.day)

        mock_blob = Mock()
        name_attr = PropertyMock(return_value=key)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        client = self.get_mock_client(blob_list=[mock_blob])
        file_path = client.download_file(key, self.container_name)
        self.assertTrue(file_path.endswith(".csv"))

    def test_download_file_with_destination(self):
        blobs = (FakeBlob("key", datetime.now()),)
        azure_client = self.get_mock_client(blob_list=blobs)
        with NamedTemporaryFile() as tf:
            file = azure_client.download_file("key", "container", destination=tf.name)

        self.assertEqual(file, tf.name)

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory)
    def test_get_file_for_key_exception(self, mock_factory):
        """Test that function handles a raised exception."""
        mock_factory.return_value = Mock(
            spec=AzureClientFactory,
            cloud_storage_account=Mock(
                return_value=Mock(
                    spec=BlobServiceClient,
                    get_container_client=Mock(
                        return_value=Mock(
                            spec=ContainerClient, list_blobs=Mock(side_effect=ClientAuthenticationError("test error"))
                        )
                    ),
                )
            ),
        )
        with self.assertRaises(AzureServiceError):
            service = AzureService(
                self.tenant_id, self.client_id, self.client_secret, self.resource_group_name, self.storage_account_name
            )
            service.get_file_for_key(key=FAKE.word(), container_name=FAKE.word())

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
                    get_blob_client=Mock(side_effect=ServiceRequestError("test error")),
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
            service.download_file(key=key, container_name=FAKE.word())

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory", spec=AzureClientFactory)
    def test_get_latest_cost_export_for_path_exception(self, mock_factory):
        """Test that function handles a raised exception."""
        mock_factory.return_value = Mock(
            spec=AzureClientFactory,
            cloud_storage_account=Mock(
                return_value=Mock(
                    spec=BlobServiceClient,
                    get_container_client=Mock(
                        return_value=Mock(
                            spec=ContainerClient, list_blobs=Mock(side_effect=ServiceRequestError("test error"))
                        )
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

    def test_get_latest_blob(self):
        """Given a list of blobs, return the blob with the latest modification date
        matching the specified extension.
        """
        report_path = "/container/report/path"
        blobs = (
            FakeBlob(f"{report_path}/file01.csv", datetime(2022, 12, 16)),
            FakeBlob(f"{report_path}/file02.csv", datetime(2022, 12, 15)),
            FakeBlob("some/other/path/file01.csv", datetime(2022, 12, 1)),
            FakeBlob(f"{report_path}/file03.csv", datetime(2022, 12, 17)),
        )
        azure_service = self.get_mock_client()
        latest_blob = azure_service._get_latest_blob(f"{report_path}", blobs, ".csv")

        self.assertEqual(latest_blob.name, f"{report_path}/file03.csv")

    def test_get_latest_cost_export_missing_container(self):
        """Test resource not found error with a missing container"""
        report_path = "{}_{}".format(self.container_name, "blob")

        mock_blob = Mock(last_modified=Mock(date=Mock(return_value=self.current_date_time.date())))
        name_attr = PropertyMock(return_value=report_path)
        type(mock_blob).name = name_attr  # kludge to set name attribute on Mock

        svc = self.get_mock_client(blob_list=[mock_blob])
        svc._cloud_storage_account.get_container_client.side_effect = ResourceNotFoundError("Oops!")
        with self.assertRaises(AzureCostReportNotFound):
            svc.get_latest_cost_export_for_path(report_path, self.container_name)

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    def test_azure_service_missing_credentials(self, mock_factory):
        """Test that AzureService raises an error if credentials are not configured."""
        mock_factory.return_value.subscription_id = "fake_subscription_id"
        mock_factory.return_value.credentials = None

        with self.assertRaises(AzureServiceError) as context:
            AzureService(
                tenant_id="fake_tenant_id",
                client_id="fake_client_id",
                client_secret="fake_client_secret",
                resource_group_name="fake_resource_group",
                storage_account_name="fake_storage_account",
                subscription_id="fake_subscription_id",
            )

        self.assertIn("Azure Service credentials are not configured.", str(context.exception))

    @patch("masu.external.downloader.azure.azure_service.AzureService._list_blobs")
    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.NamedTemporaryFile")
    def test_download_file_csv_key(self, mock_tempfile, mock_client_factory, mock_list_blobs):
        """Test that the method correctly handles a non-.gzip key (CSV)."""

        mock_blob = Mock()
        mock_blob.name = "fake_key.csv"
        mock_list_blobs.return_value = [mock_blob]

        mock_blob_client = Mock()
        mock_blob_client.download_blob.return_value.readall.return_value = b"fake_csv_data"
        mock_cloud_storage_account = Mock()
        mock_cloud_storage_account.get_blob_client.return_value = mock_blob_client
        mock_client_factory.return_value.cloud_storage_account.return_value = mock_cloud_storage_account

        mock_tempfile.return_value.name = "/tmp/fakefile.csv"

        service = AzureService(
            tenant_id="fake_tenant_id",
            client_id="fake_client_id",
            client_secret="fake_client_secret",
            resource_group_name="fake_resource_group",
            storage_account_name="fake_storage_account",
            subscription_id="fake_subscription_id",
        )

        result = service.download_file("fake_key.csv", "fake_container")

        self.assertTrue(result.endswith(".csv"))
        mock_cloud_storage_account.get_blob_client.assert_called_with("fake_container", "fake_key.csv")
        mock_blob_client.download_blob.assert_called_once()

    @patch("masu.external.downloader.azure.azure_service.AzureService._list_blobs")
    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.NamedTemporaryFile")
    def test_download_file_gzip_key(self, mock_tempfile, mock_client_factory, mock_list_blobs):
        """Test that the method correctly handles a .gzip key."""

        mock_blob = Mock()
        mock_blob.name = "fake_key.gzip"
        mock_list_blobs.return_value = [mock_blob]

        mock_blob_client = Mock()
        mock_blob_client.download_blob.return_value.readall.return_value = b"fake_gzip_data"
        mock_cloud_storage_account = Mock()
        mock_cloud_storage_account.get_blob_client.return_value = mock_blob_client
        mock_client_factory.return_value.cloud_storage_account.return_value = mock_cloud_storage_account

        mock_tempfile.return_value.name = "/tmp/fakefile.gzip"

        service = AzureService(
            tenant_id="fake_tenant_id",
            client_id="fake_client_id",
            client_secret="fake_client_secret",
            resource_group_name="fake_resource_group",
            storage_account_name="fake_storage_account",
            subscription_id="fake_subscription_id",
        )

        result = service.download_file("fake_key.gzip", "fake_container")

        self.assertTrue(result.endswith(".gzip"))
        mock_cloud_storage_account.get_blob_client.assert_called_with("fake_container", "fake_key.gzip")
        mock_blob_client.download_blob.assert_called_once()

    @patch("masu.external.downloader.azure.azure_service.AzureService._list_blobs")
    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.NamedTemporaryFile")
    def test_download_file_raises_exception(self, mock_tempfile, mock_client_factory, mock_list_blobs):
        """Test that AzureServiceError is raised when an exception occurs during download."""

        mock_blob = Mock()
        mock_blob.name = "fake_key.csv"
        mock_list_blobs.return_value = [mock_blob]

        mock_blob_client = Mock()
        mock_cloud_storage_account = Mock()

        mock_blob_client.download_blob.side_effect = AzureError("Download failed")
        mock_cloud_storage_account.get_blob_client.return_value = mock_blob_client
        mock_client_factory.return_value.cloud_storage_account.return_value = mock_cloud_storage_account

        mock_tempfile.return_value.name = "/tmp/fakefile.csv"

        service = AzureService(
            tenant_id="fake_tenant_id",
            client_id="fake_client_id",
            client_secret="fake_client_secret",
            resource_group_name="fake_resource_group",
            storage_account_name="fake_storage_account",
            subscription_id="fake_subscription_id",
        )

        with self.assertRaises(AzureServiceError) as context:
            service.download_file("fake_key.csv", "fake_container")

        self.assertIn("Failed to download cost export", str(context.exception))

    @patch("masu.external.downloader.azure.azure_service.AzureService._list_blobs")
    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.NamedTemporaryFile")
    def test_download_file_with_compression(self, mock_tempfile, mock_client_factory, mock_list_blobs):
        """Test that the method correctly handles a .gzip key with compression."""

        mock_blob = Mock()
        mock_blob.name = "fake_key.csv.gz"
        mock_list_blobs.return_value = [mock_blob]

        mock_blob_client = Mock()
        mock_blob_client.download_blob.return_value.readall.return_value = b"fake_gzip_data"
        mock_cloud_storage_account = Mock()
        mock_cloud_storage_account.get_blob_client.return_value = mock_blob_client
        mock_client_factory.return_value.cloud_storage_account.return_value = mock_cloud_storage_account

        mock_tempfile.return_value.name = "/tmp/fakefile.csv.gz"

        service = AzureService(
            tenant_id="fake_tenant_id",
            client_id="fake_client_id",
            client_secret="fake_client_secret",
            resource_group_name="fake_resource_group",
            storage_account_name="fake_storage_account",
            subscription_id="fake_subscription_id",
        )

        result = service.download_file("fake_key.csv.gz", "fake_container")

        self.assertTrue(result.endswith(".gz"))
        mock_cloud_storage_account.get_blob_client.assert_called_with("fake_container", "fake_key.csv.gz")
        mock_blob_client.download_blob.assert_called_once()
