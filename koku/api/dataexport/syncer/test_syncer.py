"""Collection of tests for the data export syncer."""
from datetime import date
from datetime import timedelta
from itertools import product
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

import faker
from botocore.exceptions import ClientError
from dateutil.rrule import DAILY
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from django.conf import settings
from django.test import TestCase

from api.dataexport.syncer import AwsS3Syncer
from api.dataexport.syncer import SyncedFileInColdStorageError
from masu.test import MasuTestCase

fake = faker.Faker()


class AwsS3SyncerTest(TestCase):
    """AwsS3Syncer test case without pre-loaded test data."""

    @patch("api.dataexport.syncer.boto3")
    def test_sync_file_fail_disabled(self, mock_boto3):
        """Test syncing a file from one S3 bucket to another fails due to it being disabled."""
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        account = fake.word()

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f"{settings.S3_BUCKET_PATH}/{account}{fake.file_path()}"
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

        mock_resource.assert_called_with("s3", settings.S3_REGION)
        mock_buckets.assert_called_once_with(source_bucket_name)
        mock_filter.assert_not_called()
        mock_destination_object.assert_not_called()
        mock_copy_from.assert_not_called()


class AwsS3SyncerTestWithData(MasuTestCase):
    """AwsS3Syncer test case with pre-loaded masu test data."""

    def get_expected_filter_calls(self, schema_name, days, months):
        """
        Get list of expected filter calls with all appropriate providers and dates.

        Args:
            schema_name (str): account schema name to sync
            days (list): list of datetime.date objects for days to sync
            months (list): list of datetime.date objects for months to sync

        Returns:
            list of expected mock.call objects.

        """
        expected_providers = [
            self.aws_provider,
            self.ocp_provider,
            self.ocp_on_aws_ocp_provider,
            self.ocp_on_azure_ocp_provider,
            self.ocp_on_gcp_ocp_provider,
            self.azure_provider,
            self.gcp_provider,
            self.oci_provider,
        ]
        expected_filter_calls = []

        for day, provider in product(days, expected_providers):
            expected_filter_calls.append(
                call(
                    Prefix=(
                        f"{settings.S3_BUCKET_PATH}/{schema_name}/"
                        f"{provider.type.lower().replace('-local', '')}/{provider.uuid}/"
                        f"{day.year:04d}/{day.month:02d}/{day.day:02d}/"
                    )
                )
            )
        for month, provider in product(months, expected_providers):
            expected_filter_calls.append(
                call(
                    Prefix=(
                        f"{settings.S3_BUCKET_PATH}/{schema_name}/"
                        f"{provider.type.replace('-local', '').lower()}/{provider.uuid}/"
                        f"{month.year:04d}/{month.month:02d}/00/"
                    )
                )
            )
        return expected_filter_calls

    @patch("api.dataexport.syncer.boto3")
    def test_sync_single_file_success(self, mock_boto3):
        """
        Test syncing a file from one S3 bucket to another succeeds.

        Also assert that all the appropriate provider filters are iterated.
        """
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        schema_name = self.schema

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        end_date = end_date - timedelta(days=1)
        days = rrule(DAILY, dtstart=start_date, until=end_date)
        months = rrule(MONTHLY, dtstart=start_date, until=end_date)

        source_object = Mock()
        source_object.key = f"{settings.S3_BUCKET_PATH}/{schema_name}{fake.file_path()}"
        source_object.bucket_name = source_bucket_name

        self.assertNotEqual(source_bucket_name, destination_bucket_name)

        mock_resource = mock_boto3.resource
        mock_buckets = mock_resource.return_value.Bucket
        mock_filter = mock_buckets.return_value.objects.filter
        mock_filter.return_value = (source_object,)
        mock_destination_object = mock_buckets.return_value.Object
        mock_copy_from = mock_destination_object.return_value.copy_from

        syncer = AwsS3Syncer(source_bucket_name)
        syncer.sync_bucket(schema_name, destination_bucket_name, date_range)

        mock_resource.assert_called_with("s3", settings.S3_REGION)
        mock_buckets.assert_any_call(source_bucket_name)
        mock_buckets.assert_any_call(destination_bucket_name)

        expected_filter_calls = self.get_expected_filter_calls(schema_name, days, months)
        mock_filter.assert_has_calls(expected_filter_calls, any_order=True)
        self.assertEqual(len(mock_filter.call_args_list), len(expected_filter_calls))

        mock_destination_object.assert_called_with(source_object.key)
        mock_copy_from.assert_called_with(
            ACL="bucket-owner-full-control", CopySource={"Bucket": source_bucket_name, "Key": source_object.key}
        )

    @patch("api.dataexport.syncer.boto3")
    def test_sync_file_fail_no_file(self, mock_boto3):
        """Test syncing a file from one S3 bucket to another fails due to no matching files."""
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        schema_name = self.schema

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
        syncer.sync_bucket(schema_name, destination_bucket_name, date_range)

        mock_resource.assert_called_with("s3", settings.S3_REGION)
        mock_buckets.assert_any_call(source_bucket_name)
        mock_buckets.assert_any_call(destination_bucket_name)

        expected_filter_calls = self.get_expected_filter_calls(schema_name, days, months)
        mock_filter.assert_has_calls(expected_filter_calls, any_order=True)
        self.assertEqual(len(mock_filter.call_args_list), len(expected_filter_calls))

        mock_destination_object.assert_not_called()
        mock_copy_from.assert_not_called()

    @patch("api.dataexport.syncer.boto3")
    def test_sync_file_in_glacier(self, mock_boto3):
        """Test syncing a file in glacier will call restore, and raise an exception."""
        client_error_glacier = ClientError(
            error_response={"Error": {"Code": "InvalidObjectState"}}, operation_name=Mock()
        )
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        schema_name = self.schema

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f"{settings.S3_BUCKET_PATH}/{schema_name}{fake.file_path()}"
        source_object.bucket_name = source_bucket_name
        source_object.storage_class = "GLACIER"

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
            syncer.sync_bucket(schema_name, destination_bucket_name, date_range)
        source_object.restore_object.assert_called()

    @patch("api.dataexport.syncer.boto3")
    def test_sync_glacier_file_restore_in_progress(self, mock_boto3):
        """Test syncing a file that is currently being restored from glacier will raise an exception."""
        restore_in_progress_error = ClientError(
            error_response={"Error": {"Code": "RestoreAlreadyInProgress"}}, operation_name=Mock()
        )
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        schema_name = self.schema

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f"{settings.S3_BUCKET_PATH}/{schema_name}{fake.file_path()}"
        source_object.bucket_name = source_bucket_name
        source_object.storage_class = "GLACIER"

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
            syncer.sync_bucket(schema_name, destination_bucket_name, date_range)
        source_object.restore_object.assert_not_called()

    @patch("api.dataexport.syncer.boto3")
    def test_sync_fail_boto3_client_exception(self, mock_boto3):
        """Test that if an client error, we raise that error."""
        client_error = ClientError(error_response={"Error": {"Code": fake.word()}}, operation_name=Mock())
        source_bucket_name = fake.slug()
        destination_bucket_name = fake.slug()
        schema_name = self.schema

        start_date = date(2019, 1, 1)
        end_date = date(2019, 3, 1)
        date_range = (start_date, end_date)

        source_object = Mock()
        source_object.key = f"{settings.S3_BUCKET_PATH}/{schema_name}{fake.file_path()}"
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
            syncer.sync_bucket(schema_name, destination_bucket_name, date_range)
        source_object.restore_object.assert_not_called()
