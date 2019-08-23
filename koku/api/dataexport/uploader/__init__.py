"""Data export uploader."""
from abc import ABC, abstractmethod

import boto3


class UploaderInterface(ABC):
    """Data uploader interface."""

    @abstractmethod
    def upload_file(self, local_path, remote_path):
        """
        Upload the file from local_path to remote_path.

        Args:
            local_path (str): source path to local file
            remote_path (str): destination path to remote file

        Returns:
            None

        """


class AwsS3Uploader(UploaderInterface):
    """Data uploader for sending files to AWS S3."""

    def __init__(self, s3_bucket_name):
        """
        Create an AwsS3Uploader.

        Args:
            s3_bucket_name (str): destination AWS S3 bucket name

        """
        self.s3_bucket_name = s3_bucket_name
        self.s3_client = boto3.client('s3')

    def upload_file(self, local_path, remote_path):
        """
        Upload a local file.

        Args:
            local_path (str): source path to local file
            remote_path (str): destination path for remote file

        """
        self.s3_client.upload_file(local_path, self.s3_bucket_name, remote_path)
