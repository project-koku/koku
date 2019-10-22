"""Data export uploader."""
import logging
from abc import ABC, abstractmethod

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)


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
        self.s3_client = boto3.client('s3', settings.S3_REGION)

    def upload_file(self, local_path, remote_path):
        """
        Upload a local file if the ENABLE_S3_ARCHIVING flag is set.

        Args:
            local_path (str): source path to local file
            remote_path (str): destination path for remote file

        """
        if settings.ENABLE_S3_ARCHIVING:
            self.s3_client.upload_file(local_path, self.s3_bucket_name, remote_path)
        else:
            logger.info(
                'Skipping upload of %s to %s; upload feature is disabled',
                local_path,
                self.s3_bucket_name,
            )
