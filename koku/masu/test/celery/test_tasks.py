"""Tests for celery tasks."""
import logging
import os
import tempfile
from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

import faker
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from celery.exceptions import Retry
from django.db import connection
from django.test import override_settings

from api.dataexport.models import DataExportRequest as APIExportRequest
from api.dataexport.syncer import SyncedFileInColdStorageError
from api.models import Provider
from api.utils import DateHelper
from masu.celery import tasks
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.orchestrator import Orchestrator
from masu.test import MasuTestCase
from masu.test.database.helpers import ManifestCreationHelper

fake = faker.Faker()
DummyS3Object = namedtuple("DummyS3Object", "key")

LOG = logging.getLogger(__name__)


class TestCeleryTasks(MasuTestCase):
    """Test cases for Celery tasks."""

    @patch("masu.celery.tasks.Orchestrator")
    def test_check_report_updates(self, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()
        tasks.check_report_updates()

        mock_orchestrator.assert_called()
        mock_orch.prepare.assert_called()

    @patch("masu.celery.tasks.Orchestrator")
    @patch("masu.external.date_accessor.DateAccessor.today")
    def test_remove_expired_data(self, mock_date, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()

        mock_date_string = "2018-07-25 00:00:30.993536"
        mock_date_obj = datetime.strptime(mock_date_string, "%Y-%m-%d %H:%M:%S.%f")
        mock_date.return_value = mock_date_obj

        tasks.remove_expired_data()

        mock_orchestrator.assert_called()
        mock_orch.remove_expired_report_data.assert_called()

    @patch("masu.celery.tasks.DataExportRequest")
    @patch("masu.celery.tasks.AwsS3Syncer")
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

    @patch("masu.celery.tasks.LOG")
    @patch("masu.celery.tasks.DataExportRequest")
    @patch("masu.celery.tasks.AwsS3Syncer")
    def test_sync_data_to_customer_fail_exc(self, mock_sync, mock_data_export_request, mock_log):
        """Test that the scheduled task correctly calls the sync function, which explodes."""
        mock_data_export_request.uuid = fake.uuid4()
        mock_data_get = mock_data_export_request.objects.get
        mock_data_save = mock_data_get.return_value.save

        mock_sync.return_value.sync_bucket.side_effect = ClientError(
            error_response={"error": fake.word()}, operation_name=fake.word()
        )

        tasks.sync_data_to_customer(mock_data_export_request.uuid)

        mock_data_get.assert_called_once_with(uuid=mock_data_export_request.uuid)
        self.assertEqual(mock_data_save.call_count, 2)
        mock_sync.assert_called_once()
        mock_sync.return_value.sync_bucket.assert_called_once()
        mock_log.exception.assert_called_once()

    @patch("masu.celery.tasks.DataExportRequest.objects")
    @patch("masu.celery.tasks.AwsS3Syncer")
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

    @patch("masu.celery.tasks.sync_data_to_customer.retry", side_effect=MaxRetriesExceededError())
    @patch("masu.celery.tasks.DataExportRequest.objects")
    @patch("masu.celery.tasks.AwsS3Syncer")
    def test_sync_data_to_customer_max_retry(self, mock_sync, mock_data_export_request, mock_retry):
        """Test that the sync task retries syncer fails with a cold storage error."""
        data_export_object = Mock()
        data_export_object.uuid = fake.uuid4()
        data_export_object.status = APIExportRequest.PENDING

        mock_data_export_request.get.return_value = data_export_object
        mock_sync.return_value.sync_bucket.side_effect = SyncedFileInColdStorageError()

        tasks.sync_data_to_customer(data_export_object.uuid)
        self.assertEquals(data_export_object.status, APIExportRequest.ERROR)

    @override_settings(ENABLE_S3_ARCHIVING=True)
    def test_delete_archived_data_bad_inputs_exception(self):
        """Test that delete_archived_data raises an exception when given bad inputs."""
        schema_name, provider_type, provider_uuid = "", "", ""
        with self.assertRaises(TypeError) as e:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        self.assertIn("schema_name", str(e.exception))
        self.assertIn("provider_type", str(e.exception))
        self.assertIn("provider_uuid", str(e.exception))

    @patch("masu.util.aws.common.boto3.resource")
    @override_settings(ENABLE_S3_ARCHIVING=False)
    def test_delete_archived_data_archiving_disabled_noop(self, mock_resource):
        """Test that delete_archived_data returns early when feature is disabled."""
        schema_name, provider_type, provider_uuid = fake.slug(), Provider.PROVIDER_AWS, fake.uuid4()
        tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_resource.assert_not_called()

    @override_settings(ENABLE_S3_ARCHIVING=True)
    @patch("masu.celery.tasks.get_s3_resource")
    def test_delete_archived_data_success(self, mock_resource):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = "acct10001"
        provider_type = Provider.PROVIDER_AWS
        provider_uuid = "00000000-0000-0000-0000-000000000001"
        expected_prefix = "data/csv/10001/00000000-0000-0000-0000-000000000001/"

        # Generate enough fake objects to expect calling the S3 delete api twice.
        mock_bucket = mock_resource.return_value.Bucket.return_value
        bucket_objects = [DummyS3Object(key=fake.file_path()) for _ in range(1234)]
        expected_keys = [{"Key": bucket_object.key} for bucket_object in bucket_objects]

        # Leave one object mysteriously not deleted to cover the LOG.warning use case.
        mock_bucket.objects.filter.side_effect = [bucket_objects, bucket_objects[:1]]

        with self.assertLogs("masu.celery.tasks", "WARNING") as captured_logs:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_resource.assert_called()
        mock_bucket.delete_objects.assert_has_calls(
            [call(Delete={"Objects": expected_keys[:1000]}), call(Delete={"Objects": expected_keys[1000:]})]
        )
        mock_bucket.objects.filter.assert_has_calls([call(Prefix=expected_prefix), call(Prefix=expected_prefix)])
        self.assertIn("Found 1 objects after attempting", captured_logs.output[-1])

    @override_settings(ENABLE_S3_ARCHIVING=False)
    def test_delete_archived_data_archiving_false(self):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = "acct10001"
        provider_type = Provider.PROVIDER_AWS
        provider_uuid = "00000000-0000-0000-0000-000000000001"

        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
            self.assertIn("Skipping delete_archived_data. Upload feature is disabled.", captured_logs.output[0])

    @patch("masu.celery.tasks.vacuum_schema")
    def test_vacuum_schemas(self, mock_vacuum):
        """Test that the vacuum_schemas scheduled task runs for all schemas."""
        schema_one = "acct123"
        schema_two = "acct456"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_tenant (schema_name)
                VALUES (%s), (%s)
                """,
                [schema_one, schema_two],
            )

        tasks.vacuum_schemas()

        for schema_name in [schema_one, schema_two]:
            mock_vacuum.delay.assert_any_call(schema_name)

    @patch("masu.celery.tasks.Config")
    @patch("masu.external.date_accessor.DateAccessor.get_billing_months")
    def test_clean_volume(self, mock_date, mock_config):
        """Test that the clean volume function is cleaning the appropriate files"""
        # create a manifest
        mock_date.return_value = ["2020-02-01"]
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": "2020-02-01",
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.add(**manifest_dict)
        # create two files on the temporary volume one with a matching prefix id
        #  as the assembly_id in the manifest above
        with tempfile.TemporaryDirectory() as tmpdirname:
            mock_config.PVC_DIR = tmpdirname
            mock_config.VOLUME_FILE_RETENTION = 60 * 60 * 24
            old_matching_file = os.path.join(tmpdirname, "%s.csv" % manifest.assembly_id)
            new_no_match_file = os.path.join(tmpdirname, "newfile.csv")
            old_no_match_file = os.path.join(tmpdirname, "oldfile.csv")
            filepaths = [old_matching_file, new_no_match_file, old_no_match_file]
            for path in filepaths:
                open(path, "a").close()
                self.assertEqual(os.path.exists(path), True)

            # Update timestame for oldfile.csv
            datehelper = DateHelper()
            now = datehelper.now
            old_datetime = now - timedelta(seconds=mock_config.VOLUME_FILE_RETENTION * 2)
            oldtime = old_datetime.timestamp()
            os.utime(old_matching_file, (oldtime, oldtime))
            os.utime(old_no_match_file, (oldtime, oldtime))

            # now run the clean volume task
            tasks.clean_volume()
            # make sure that the file with the matching id still exists and that
            # the file with the other id is gone
            self.assertEqual(os.path.exists(old_matching_file), True)
            self.assertEqual(os.path.exists(new_no_match_file), True)
            self.assertEqual(os.path.exists(old_no_match_file), False)
            # now edit the manifest to say that all the files have been processed
            # and rerun the clean_volumes task
            manifest.num_processed_files = manifest_dict.get("num_total_files")
            manifest_helper = ManifestCreationHelper(
                manifest.id, manifest_dict.get("num_total_files"), manifest_dict.get("assembly_id")
            )
            manifest_helper.generate_test_report_files()
            manifest_helper.process_all_files()

            manifest.save()
            tasks.clean_volume()
            # ensure that the original file is deleted from the volume
            self.assertEqual(os.path.exists(old_matching_file), False)
            self.assertEqual(os.path.exists(new_no_match_file), True)

        # assert the tempdir is cleaned up
        self.assertEqual(os.path.exists(tmpdirname), False)
        # test no files found for codecov
        tasks.clean_volume()

    @patch("masu.celery.tasks.AWSOrgUnitCrawler")
    def test_crawl_account_hierarchy_with_provider_uuid(self, mock_crawler):
        """Test that only accounts associated with the provider_uuid are polled."""
        mock_crawler.crawl_account_hierarchy.return_value = True
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.crawl_account_hierarchy(self.aws_test_provider_uuid)
            expected_log_msg = "Account hierarchy crawler found %s accounts to scan" % ("1")
            self.assertIn(expected_log_msg, captured_logs.output[0])

    @patch("masu.celery.tasks.AWSOrgUnitCrawler")
    def test_crawl_account_hierarchy_without_provider_uuid(self, mock_crawler):
        """Test that all polling accounts for user are used when no provider_uuid is provided."""
        _, polling_accounts = Orchestrator.get_accounts()
        mock_crawler.crawl_account_hierarchy.return_value = True
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.crawl_account_hierarchy()
            expected_log_msg = "Account hierarchy crawler found %s accounts to scan" % (len(polling_accounts))
            self.assertIn(expected_log_msg, captured_logs.output[0])
