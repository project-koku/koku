"""Collection of tests for the data export uploader."""
import logging
from unittest.mock import patch

import faker
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings

from api.dataexport.uploader import AwsS3Uploader

fake = faker.Faker()


class DummyException(Exception):
    """Dummy exception for testing."""


@override_settings(ENABLE_S3_ARCHIVING=True)
class AwsS3UploaderTest(TestCase):
    """AwsS3Uploader test case."""

    @classmethod
    def setUpClass(cls):
        """Test Class setup."""
        super().setUpClass()
        # We need to see all expected logs for tests here.
        logging.disable(logging.NOTSET)

    @patch("api.dataexport.uploader.boto3")
    def test_upload_file_success(self, mock_boto3):
        """Test uploading a file to AWS S3."""
        bucket_name = fake.slug()
        local_path = fake.file_path()
        remote_path = fake.file_path()
        self.assertNotEqual(local_path, remote_path)

        uploader = AwsS3Uploader(bucket_name)
        uploader.upload_file(local_path, remote_path)

        mock_boto3.client.assert_called_with("s3", settings.S3_REGION)
        mock_client = mock_boto3.client.return_value
        mock_client.upload_file.assert_called_with(local_path, bucket_name, remote_path)

    @patch("api.dataexport.uploader.boto3")
    def test_upload_file_exception(self, mock_boto3):
        """Test uploading a file to AWS S3 when boto3 raises an exception."""
        bucket_name = fake.slug()
        local_path = fake.file_path()
        remote_path = fake.file_path()
        self.assertNotEqual(local_path, remote_path)

        mock_client = mock_boto3.client.return_value
        exception_message = "something broke"
        mock_client.upload_file.side_effect = DummyException(exception_message)

        uploader = AwsS3Uploader(bucket_name)
        with self.assertRaises(DummyException) as the_exception, self.assertLogs(
            "api.dataexport.uploader", "ERROR"
        ) as capture_logs:
            uploader.upload_file(local_path, remote_path)
        self.assertEqual(str(the_exception.exception), exception_message)
        self.assertIn("Failed to upload", capture_logs.output[0])

        mock_boto3.client.assert_called_with("s3", settings.S3_REGION)
        mock_client.upload_file.assert_called_with(local_path, bucket_name, remote_path)
