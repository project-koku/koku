"""Collection of tests for the data export syncer."""
from datetime import date, timedelta
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from dateutil.rrule import DAILY, MONTHLY, rrule
from django.conf import settings
from django.test import TestCase

from api.dataexport.syncer import AwsS3Syncer, SyncedFileInColdStorageError

fake = faker.Faker()


class AwsS3SyncerTest(TestCase):
    """AwsS3Syncer test case."""

    @patch('api.dataexport.syncer.boto3')
    def test_sync_file_success(self, mock_boto3):
        """Test syncing a file from one S3 bucket to another succeeds."""
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        end_date = end_date - timedelta(days=1)
        days = rrule(DAILY, dtstart=start_date, until=end_date)
        months = rrule(MONTHLY, dtstart=start_date, until=end_date)

        source_object = Mock()
        source_object.key = f'{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}'
        source_object.bucket_name = source_bucket_name

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from

        syncer = AwsS3Syncer(source_bucket_name)
        syncer.sync_bucket(account, destination_bucket_name, date_range)

        mock_resource.assert_called_with('s3', settings.S3_REGION)
        mock_buckets.assert_any_call(source_bucket_name)
        mock_buckets.assert_any_call(destination_bucket_name)

        for day in days:
            mock_filter.assert_any_call(Prefix=f'{settings.S3_BUCKET_PATH}/{account}/{day.month:02d}/{day.day:02d}/')
        for month in months:
            mock_filter.assert_any_call(Prefix=f'{settings.S3_BUCKET_PATH}/{account}/{month.month:02d}/00/')

        mock_destination_object.assert_called_with(source_object.key)
        mock_copy_from.assert_called_with(
            ACL='bucket-owner-full-control',
            CopySource={'Bucket': source_bucket_name, 'Key': source_object.key})

    @patch('api.dataexport.syncer.boto3')
    def test_sync_file_fail_disabled(self, mock_boto3):
        """Test syncing a file from one S3 bucket to another fails due to it being disabled."""
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f'{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}'
        source_object.bucket_name = source_bucket_name

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from

        with self.settings(ENABLE_S3_ARCHIVING=False):
            syncer = AwsS3Syncer(source_bucket_name)
            syncer.sync_bucket(account, destination_bucket_name, date_range)

        mock_resource.assert_called_with('s3', settings.S3_REGION)
        mock_buckets.assert_called_once_with(source_bucket_name)
        mock_filter.assert_not_called()
        mock_destination_object.assert_not_called()
        mock_copy_from.assert_not_called()

    @patch('api.dataexport.syncer.boto3')
    def test_sync_file_fail_no_file(self, mock_boto3):
        """Test syncing a file from one S3 bucket to another fails due to no matching files."""
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        end_date = end_date - timedelta(days=1)
        days = rrule(DAILY, dtstart=start_date, until=end_date)
        months = rrule(MONTHLY, dtstart=start_date, until=end_date)

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = ()
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from

        syncer = AwsS3Syncer(source_bucket_name)
        syncer.sync_bucket(account, destination_bucket_name, date_range)

        mock_resource.assert_called_with('s3', settings.S3_REGION)
        mock_buckets.assert_any_call(source_bucket_name)
        mock_buckets.assert_any_call(destination_bucket_name)

        for day in days:
            mock_filter.assert_any_call(Prefix=f'{settings.S3_BUCKET_PATH}/{account}/{day.month:02d}/{day.day:02d}/')
        for month in months:
            mock_filter.assert_any_call(Prefix=f'{settings.S3_BUCKET_PATH}/{account}/{month.month:02d}/00/')

        mock_destination_object.assert_not_called()
        mock_copy_from.assert_not_called()

    @patch('api.dataexport.syncer.boto3')
    def test_sync_file_in_glacier(self, mock_boto3):
        """Test syncing a file in glacier will call restore, and raise an exception."""
        client_error_glacier = ClientError(
            error_response={'Error': {'Code': 'InvalidObjectState'}},
            operation_name=Mock(),
        )
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f'{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}'
        source_object.bucket_name = source_bucket_name
        source_object.storage_class = 'GLACIER'

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from
        mock_copy_from.side_effect = client_error_glacier
        with self.assertRaises(SyncedFileInColdStorageError):
            syncer = AwsS3Syncer(source_bucket_name)
            syncer.sync_bucket(account, destination_bucket_name, date_range)
        source_object.restore_object.assert_called()

    @patch('api.dataexport.syncer.boto3')
    def test_sync_glacier_file_restore_in_progress(self, mock_boto3):
        """Test syncing a file that is currently being restored from glacier will raise an exception."""
        restore_in_progress_error = ClientError(
            error_response={'Error': {'Code': 'RestoreAlreadyInProgress'}},
            operation_name=Mock(),
        )
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f'{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}'
        source_object.bucket_name = source_bucket_name
        source_object.storage_class = 'GLACIER'

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from
        mock_copy_from.side_effect = restore_in_progress_error

        with self.assertRaises(SyncedFileInColdStorageError):
            syncer = AwsS3Syncer(source_bucket_name)
            syncer.sync_bucket(account, destination_bucket_name, date_range)
        source_object.restore_object.assert_not_called()

    @patch('api.dataexport.syncer.boto3')
    def test_sync_fail_boto3_client_exception(self, mock_boto3):
        """Test that if an client error, we raise that error."""
        client_error = ClientError(
            error_response={'Error': {'Code': fake.word()}},
            operation_name=Mock(),
        )
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f'{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}'
        source_object.bucket_name = source_bucket_name
        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from
        mock_copy_from.side_effect = client_error

        with self.assertRaises(ClientError):
            syncer = AwsS3Syncer(source_bucket_name)
            syncer.sync_bucket(account, destination_bucket_name, date_range)
        source_object.restore_object.assert_not_called()
