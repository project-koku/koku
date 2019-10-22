"""Data export syncer."""
from abc import ABC, abstractmethod
from datetime import timedelta
from itertools import product

import boto3
from botocore.exceptions import ClientError
from celery.utils.log import get_task_logger
from dateutil.rrule import DAILY, MONTHLY, rrule
from django.conf import settings
from django.utils.translation import gettext as _

LOG = get_task_logger(__name__)
_PROVIDER_TYPES = ['aws', 'ocp', 'azure']


class SyncedFileInColdStorageError(Exception):
    """
    Syncer Error raised when the file we're attempting to sync is in cold storage.

    This occurs when a file is in a cold archival storage and cannot be synced.

    In AWS this is 'Glacier' storage
    In Azure this is 'Cool Blob Storage'
    In GCP this is 'coldline' storage

    """


class SyncerInterface(ABC):
    """Data syncer interface."""

    @abstractmethod
    def sync_bucket(self, account, destination_bucket_name, date_range):
        """
        Sync all files in our bucket for one account to customer account.

        Args:
            account (str): account to sync
            destination_bucket_name (str): name of the customer bucket
            date_range (tuple): Pair of date objects of inclusive start and exclusive end dates for which to sync data.

        Returns:
            None

        """


class AwsS3Syncer(SyncerInterface):
    """Data syncer for syncing files in S3."""

    def __init__(self, s3_source_bucket_name):
        """
        Create an AwsS3Syncer.

        Args:
            s3_source_bucket_name (str): name of the our bucket

        """
        self.s3_resource = boto3.resource('s3', settings.S3_REGION)
        self.s3_source_bucket = self.s3_resource.Bucket(s3_source_bucket_name)

    def _copy_object(self, s3_destination_bucket, source_object):
        """
        Copy a source object to the destination bucket.

        Args:
            s3_destination_bucket (boto3.s3.Bucket): the destination bucket object
            source_object (boto3.s3.Object): our source object

        """
        try:
            destination_object = s3_destination_bucket.Object(source_object.key)
            destination_object.copy_from(
                ACL='bucket-owner-full-control',
                CopySource={'Bucket': source_object.bucket_name, 'Key': source_object.key})
        except ClientError as e:
            # If we run into an InvalidObjectState error, and object is in glacier, retrieve it
            if source_object.storage_class == 'GLACIER' and e.response['Error']['Code'] == 'InvalidObjectState':
                request = {'Days': 2,
                           'GlacierJobParameters': {'Tier': 'Standard'}}
                source_object.restore_object(RestoreRequest=request)
                LOG.info(_('Glacier Storage restore for %s is in progress.'), source_object.key)
                raise SyncedFileInColdStorageError(
                    f'Requested file {source_object.key} is currently in AWS Glacier Storage, '
                    f'an request has been made to restore the file.'
                )
            # if object cannot be copied because restore is already in progress raise
            # SyncedFileInColdStorageError and wait a while longer
            elif e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
                LOG.info(_('Glacier Storage restore for %s is in progress.'), source_object.key)
                raise SyncedFileInColdStorageError(
                    f'Requested file {source_object.key} has not yet been restored from AWS Glacier Storage.'
                )
            raise e

    def sync_bucket(self, account, s3_destination_bucket_name, date_range):
        """
        Sync buckets if the ENABLE_S3_ARCHIVING flag is set.

        Args:
            account (str): account to sync
            s3_destination_bucket_name (str): name of the customer bucket
            date_range (tuple): Pair of date objects of inclusive start and exclusive end dates for which to sync data.

        """
        if settings.ENABLE_S3_ARCHIVING:
            start_date, end_date = date_range
            # rrule is inclusive for both dates, so we need to make end_date exclusive
            end_date = end_date - timedelta(days=1)
            days = rrule(DAILY, dtstart=start_date, until=end_date)
            months = rrule(MONTHLY, dtstart=start_date, until=end_date)
            s3_destination_bucket = self.s3_resource.Bucket(s3_destination_bucket_name)

            # Copy the specific month level files
            for month, provider_type in product(months, _PROVIDER_TYPES):
                for source_object in self.s3_source_bucket.objects.filter(
                    Prefix=(
                        f'{settings.S3_BUCKET_PATH}/{account}/{provider_type}/'
                        f'{month.year:04d}/{month.month:02d}/00/'
                    )
                ):
                    self._copy_object(s3_destination_bucket, source_object)

            # Copy all the day files
            for day, provider_type in product(days, _PROVIDER_TYPES):
                for source_object in self.s3_source_bucket.objects.filter(
                    Prefix=(
                        f'{settings.S3_BUCKET_PATH}/{account}/{provider_type}/'
                        f'{day.year:04d}/{day.month:02d}/{day.day:02d}/'
                    )
                ):
                    self._copy_object(s3_destination_bucket, source_object)
