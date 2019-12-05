"""Tests for celery tasks."""
import uuid
from collections import namedtuple
from datetime import date, datetime
from unittest.mock import Mock, call, patch

import faker
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError, Retry
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from api.dataexport.models import DataExportRequest as APIExportRequest
from api.dataexport.syncer import SyncedFileInColdStorageError
from masu.celery import tasks
from masu.test import MasuTestCase

fake = faker.Faker()
DummyS3Object = namedtuple('DummyS3Object', 'key')


class TestCeleryTasks(MasuTestCase):
    """Test cases for Celery tasks."""

    @patch('masu.celery.tasks.Orchestrator')
    def test_check_report_updates(self, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()
        tasks.check_report_updates()

        mock_orchestrator.assert_called()
        mock_orch.prepare.assert_called()

    @patch('masu.celery.tasks.Orchestrator')
    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_remove_expired_data(self, mock_date, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()

        mock_date_string = '2018-07-25 00:00:30.993536'
        mock_date_obj = datetime.strptime(mock_date_string, '%Y-%m-%d %H:%M:%S.%f')
        mock_date.return_value = mock_date_obj

        tasks.remove_expired_data()

        mock_orchestrator.assert_called()
        mock_orch.remove_expired_report_data.assert_called()

    @patch('masu.celery.tasks.Orchestrator')
    @patch('masu.celery.tasks.query_and_upload_to_s3')
    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_upload_normalized_data(self, mock_date, mock_upload, mock_orchestrator):
        """Test that the scheduled task uploads the correct normalized data."""
        test_export_setting = {
            'provider': 'test',
            'table_name': 'test',
            'sql': 'test_sql',
        }
        schema_name = 'acct10001'
        provider_uuid = uuid.uuid4()

        mock_date.return_value = date(2015, 1, 5)

        mock_orchestrator.get_accounts.return_value = (
            [{'schema_name': schema_name, 'provider_uuid': provider_uuid}],
            [],
        )

        current_month_start = date(2015, 1, 1)
        current_month_end = date(2015, 1, 31)
        prev_month_start = date(2014, 12, 1)
        prev_month_end = date(2014, 12, 31)

        call_curr_month = call(
            schema_name,
            provider_uuid,
            test_export_setting,
            (current_month_start, current_month_end),
        )
        call_prev_month = call(
            schema_name, provider_uuid, test_export_setting, (prev_month_start, prev_month_end),
        )

        with patch('masu.celery.tasks.table_export_settings', [test_export_setting]):
            tasks.upload_normalized_data()
            mock_upload.assert_has_calls([call_curr_month, call_prev_month])

        mock_date.return_value = date(2012, 3, 31)
        current_month_start = date(2012, 3, 1)
        current_month_end = date(2012, 3, 31)
        prev_month_start = date(2012, 2, 1)
        prev_month_end = date(2012, 2, 29)

        call_curr_month = call(
            schema_name,
            provider_uuid,
            test_export_setting,
            (current_month_start, current_month_end),
        )
        call_prev_month = call(
            schema_name, provider_uuid, test_export_setting, (prev_month_start, prev_month_end),
        )

        with patch('masu.celery.tasks.table_export_settings', [test_export_setting]):
            tasks.upload_normalized_data()
            mock_upload.assert_has_calls([call_curr_month, call_prev_month])

    @patch('masu.celery.tasks.DataExportRequest')
    @patch('masu.celery.tasks.AwsS3Syncer')
    def test_sync_data_to_customer_success(self, mock_sync, mock_data_export_request):
        """Test that the scheduled task correctly calls the sync function."""
        mock_data_export_request.uuid = fake.uuid4()
        mock_data_get = mock_data_export_request.objects.get
        mock_data_save = mock_data_get.return_value.save

        tasks.sync_data_to_customer(mock_data_export_request.uuid)

        mock_data_get.assert_called_once_with(uuid=mock_data_export_request.uuid)
        self.assertEqual(mock_data_save.call_count, 2)
        mock_sync.assert_called_once()
        mock_sync.return_value.sync_bucket.assert_called_once()

    @patch('masu.celery.tasks.LOG')
    @patch('masu.celery.tasks.DataExportRequest')
    @patch('masu.celery.tasks.AwsS3Syncer')
    def test_sync_data_to_customer_fail_exc(self, mock_sync, mock_data_export_request, mock_log):
        """Test that the scheduled task correctly calls the sync function, which explodes."""
        mock_data_export_request.uuid = fake.uuid4()
        mock_data_get = mock_data_export_request.objects.get
        mock_data_save = mock_data_get.return_value.save

        mock_sync.return_value.sync_bucket.side_effect = ClientError(
            error_response={'error': fake.word()}, operation_name=fake.word()
        )

        tasks.sync_data_to_customer(mock_data_export_request.uuid)

        mock_data_get.assert_called_once_with(uuid=mock_data_export_request.uuid)
        self.assertEqual(mock_data_save.call_count, 2)
        mock_sync.assert_called_once()
        mock_sync.return_value.sync_bucket.assert_called_once()
        mock_log.exception.assert_called_once()

    @patch('masu.celery.tasks.DataExportRequest.objects')
    @patch('masu.celery.tasks.AwsS3Syncer')
    def test_sync_data_to_customer_cold_storage_retry(self, mock_sync, mock_data_export_request):
        """Test that the sync task retries syncer fails with a cold storage error."""
        data_export_object = Mock()
        data_export_object.uuid = fake.uuid4()
        data_export_object.status = APIExportRequest.PENDING

        mock_data_export_request.get.return_value = data_export_object
        mock_sync.return_value.sync_bucket.side_effect = SyncedFileInColdStorageError()
        with self.assertRaises(Retry):
            tasks.sync_data_to_customer(data_export_object.uuid)
        self.assertEquals(data_export_object.status, APIExportRequest.WAITING)

    @patch('masu.celery.tasks.sync_data_to_customer.retry', side_effect=MaxRetriesExceededError())
    @patch('masu.celery.tasks.DataExportRequest.objects')
    @patch('masu.celery.tasks.AwsS3Syncer')
    def test_sync_data_to_customer_max_retry(self, mock_sync, mock_data_export_request, mock_retry):
        """Test that the sync task retries syncer fails with a cold storage error."""
        data_export_object = Mock()
        data_export_object.uuid = fake.uuid4()
        data_export_object.status = APIExportRequest.PENDING

        mock_data_export_request.get.return_value = data_export_object
        mock_sync.return_value.sync_bucket.side_effect = SyncedFileInColdStorageError()

        tasks.sync_data_to_customer(data_export_object.uuid)
        self.assertEquals(data_export_object.status, APIExportRequest.ERROR)

    def test_delete_archived_data_bad_inputs_exception(self):
        """Test that delete_archived_data raises an exception when given bad inputs."""
        schema_name, provider_type, provider_uuid = '', '', ''
        with self.assertRaises(TypeError) as e:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        self.assertIn('schema_name', str(e.exception))
        self.assertIn('provider_type', str(e.exception))
        self.assertIn('provider_uuid', str(e.exception))

    @patch('masu.util.aws.common.boto3.resource')
    @override_settings(ENABLE_S3_ARCHIVING=False)
    def test_delete_archived_data_archiving_disabled_noop(self, mock_resource):
        """Test that delete_archived_data returns early when feature is disabled."""
        schema_name, provider_type, provider_uuid = fake.slug(), 'AWS', fake.uuid4()
        tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_resource.assert_not_called()

    @patch('masu.util.aws.common.boto3.resource')
    @override_settings(S3_BUCKET_PATH='')
    def test_delete_archived_data_missing_bucket_path_exception(self, mock_resource):
        """Test that delete_archived_data raises an exception with an empty bucket path."""
        schema_name, provider_type, provider_uuid = fake.slug(), 'AWS', fake.uuid4()
        with self.assertRaises(ImproperlyConfigured):
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_resource.assert_not_called()

    @patch('masu.util.aws.common.boto3.resource')
    @override_settings(S3_BUCKET_PATH='data_archive')
    def test_delete_archived_data_success(self, mock_resource):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = 'acct10001'
        provider_type = 'AWS'
        provider_uuid = '00000000-0000-0000-0000-000000000001'
        expected_prefix = 'data_archive/acct10001/aws/00000000-0000-0000-0000-000000000001/'

        # Generate enough fake objects to expect calling the S3 delete api twice.
        mock_bucket = mock_resource.return_value.Bucket.return_value
        bucket_objects = [DummyS3Object(key=fake.file_path()) for _ in range(1234)]
        expected_keys = [{'Key': bucket_object.key} for bucket_object in bucket_objects]

        # Leave one object mysteriously not deleted to cover the LOG.warning use case.
        mock_bucket.objects.filter.side_effect = [bucket_objects, bucket_objects[:1]]

        with self.assertLogs('masu.celery.tasks', 'WARNING') as captured_logs:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_resource.assert_called()
        mock_bucket.delete_objects.assert_has_calls(
            [
                call(Delete={'Objects': expected_keys[:1000]}),
                call(Delete={'Objects': expected_keys[1000:]}),
            ]
        )
        mock_bucket.objects.filter.assert_has_calls(
            [call(Prefix=expected_prefix), call(Prefix=expected_prefix)]
        )
        self.assertIn('Found 1 objects after attempting', captured_logs.output[-1])
