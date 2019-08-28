"""Collection of tests for the data export uploader."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.dataexport.uploader import AwsS3Uploader

fake = faker.Faker()


class AwsS3UploaderTest(TestCase):
    """AwsS3Uploader test case."""

    @patch('api.dataexport.uploader.boto3')
    def test_upload_file(self, mock_boto3):
        """Test uploading a file to AWS S3."""
        bucket_name = fake.slug()
        local_path = fake.file_path()
        remote_path = fake.file_path()
        self.assertNotEqual(local_path, remote_path)

        uploader = AwsS3Uploader(bucket_name)
        uploader.upload_file(local_path, remote_path)

        mock_boto3.client.assert_called_with('s3')
        mock_client = mock_boto3.client.return_value
        mock_client.upload_file.assert_called_with(local_path, bucket_name, remote_path)
