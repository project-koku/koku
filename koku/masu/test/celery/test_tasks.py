"""Tests for celery tasks."""
from collections import namedtuple
from datetime import datetime
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

import faker
import requests_mock
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from celery.exceptions import Retry
from django.conf import settings
from django.test import override_settings
from model_bakery import baker
from requests.exceptions import HTTPError

from api.currency.models import ExchangeRates
from api.dataexport.models import DataExportRequest as APIExportRequest
from api.dataexport.syncer import SyncedFileInColdStorageError
from api.models import Provider
from masu.celery import tasks
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.prometheus_stats import QUEUES
from masu.test import MasuTestCase
from reporting.models import TRINO_MANAGED_TABLES

fake = faker.Faker()
DummyS3Object = namedtuple("DummyS3Object", "key")


class FakeManifest:
    def get_manifest_list_for_provider_and_bill_date(self, provider_uuid, bill_date):
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": "2020-02-01",
            "num_total_files": 2,
            "provider_uuid": provider_uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.add(**manifest_dict)
        return [manifest]

    def get_manifest_list_for_provider_and_date_range(self, provider_uuid, start_date, end_date):
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": "2020-02-01",
            "num_total_files": 2,
            "provider_uuid": provider_uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.add(**manifest_dict)
        return [manifest]

    def bulk_delete_manifests(self, provider_uuid, manifest_id_list):
        return True


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

        self.assertEqual(data_export_object.status, APIExportRequest.WAITING)

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
        self.assertEqual(data_export_object.status, APIExportRequest.ERROR)

    # Check to see if exchange rates are being created or updated
    def test_get_currency_conversion_rates(self):
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.get_daily_currency_rates()

        self.assertIn("Creating the exchange rate" or "Updating currency", str(captured_logs))

    def test_error_get_currency_conversion_rates(self):
        with self.assertLogs("masu.celery.tasks", "ERROR") as captured_logs:
            with requests_mock.Mocker() as reqmock:
                reqmock.register_uri("GET", settings.CURRENCY_URL, exc=HTTPError("Raised intentionally"))
                result = tasks.get_daily_currency_rates()

        self.assertEqual({}, result)
        self.assertIn("Couldn't pull latest conversion rates", captured_logs.output[0])
        self.assertIn("Raised intentionally", captured_logs.output[1])

    def test_get_currency_conversion_rates_successful(self):
        beforeRows = ExchangeRates.objects.count()
        self.assertEqual(beforeRows, 2)

        result = {
            "result": "success",
            "rates": {"AUD": 1.37, "CAD": 1.25, "CHF": 0.928},
        }
        with requests_mock.Mocker() as reqmock:
            reqmock.register_uri("GET", settings.CURRENCY_URL, status_code=201, json=result)
            tasks.get_daily_currency_rates()

        afterRows = ExchangeRates.objects.count()
        self.assertEqual(afterRows, 5)

    def test_get_currency_conversion_rates_unsupported_currency(self):
        beforeRows = ExchangeRates.objects.count()
        self.assertEqual(beforeRows, 2)

        result = {
            "result": "success",
            "rates": {"AUD": 1.37, "CAD": 1.25, "CHF": 0.928, "FOO": 12.34},
        }
        with requests_mock.Mocker() as reqmock:
            reqmock.register_uri("GET", settings.CURRENCY_URL, status_code=201, json=result)
            tasks.get_daily_currency_rates()

        afterRows = ExchangeRates.objects.count()
        self.assertEqual(afterRows, 5)

    def test_delete_archived_data_bad_inputs_exception(self):
        """Test that delete_archived_data raises an exception when given bad inputs."""
        schema_name, provider_type, provider_uuid = "", "", ""
        with self.assertRaises(TypeError) as e:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)

        self.assertIn("schema_name", str(e.exception))
        self.assertIn("provider_type", str(e.exception))
        self.assertIn("provider_uuid", str(e.exception))

    @patch("masu.celery.tasks.get_s3_resource")
    def test_deleted_archived_with_prefix_success(self, mock_resource):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        expected_prefix = "data/csv/10001/00000000-0000-0000-0000-000000000001/"

        # Generate enough fake objects to expect calling the S3 delete api twice.
        mock_bucket = mock_resource.return_value.Bucket.return_value
        bucket_objects = [DummyS3Object(key=fake.file_path()) for _ in range(1234)]
        expected_keys = [{"Key": bucket_object.key} for bucket_object in bucket_objects]

        # Leave one object mysteriously not deleted to cover the LOG.warning use case.
        mock_bucket.objects.filter.side_effect = [bucket_objects, bucket_objects[:1]]

        with self.assertLogs("masu.celery.tasks", "WARNING") as captured_logs:
            tasks.deleted_archived_with_prefix(mock_bucket, expected_prefix)
        mock_resource.assert_called()
        mock_bucket.delete_objects.assert_has_calls(
            [call(Delete={"Objects": expected_keys[:1000]}), call(Delete={"Objects": expected_keys[1000:]})]
        )
        mock_bucket.objects.filter.assert_has_calls([call(Prefix=expected_prefix), call(Prefix=expected_prefix)])
        self.assertIn("Found 1 objects after attempting", captured_logs.output[-1])

    @patch("masu.celery.tasks.deleted_archived_with_prefix")
    def test_delete_archived_data_success(self, mock_delete):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = "org1234567"
        provider_type = Provider.PROVIDER_AWS
        provider_uuid = "00000000-0000-0000-0000-000000000001"

        tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_delete.assert_called()

    @override_settings(SKIP_MINIO_DATA_DELETION=True)
    def test_delete_archived_data_minio(self):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = "org1234567"
        provider_type = Provider.PROVIDER_AWS
        provider_uuid = "00000000-0000-0000-0000-000000000001"

        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.delete_archived_data(schema_name, provider_type, provider_uuid)

        self.assertIn("Skipping delete_archived_data. MinIO in use.", captured_logs.output[0])

    @patch("masu.celery.tasks.OCPReportDBAccessor.delete_hive_partitions_by_source")
    @patch("masu.celery.tasks.deleted_archived_with_prefix")
    def test_delete_archived_data_ocp_delete_trino_partitions(self, mock_delete, mock_delete_partitions):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        schema_name = "org1234567"
        provider_type = Provider.PROVIDER_OCP
        provider_uuid = "00000000-0000-0000-0000-000000000001"

        tasks.delete_archived_data(schema_name, provider_type, provider_uuid)
        mock_delete.assert_called()
        calls = []
        for table, partition_column in TRINO_MANAGED_TABLES.items():
            calls.append(call(table, partition_column, provider_uuid))
        mock_delete_partitions.assert_has_calls(calls)

    def test_crawl_account_hierarchy_with_provider_uuid(self):
        """Test that only accounts associated with the provider_uuid are polled."""
        p = baker.make(Provider, type=Provider.PROVIDER_AWS)
        with patch.object(AWSOrgUnitCrawler, "crawl_account_hierarchy") as mock_crawler:
            mock_crawler.return_value = True
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.crawl_account_hierarchy(p.uuid)
            expected_log_msg = "Account hierarchy crawler found 1 accounts to scan"

        self.assertIn(expected_log_msg, captured_logs.output[0])

    def test_crawl_account_hierarchy_without_provider_uuid(self):
        """Test that all polling accounts for user are used when no provider_uuid is provided."""
        baker.make(Provider, type=Provider.PROVIDER_AWS)
        polling_accounts = Provider.polling_objects.all()
        providers = Provider.objects.all()
        for provider in providers:
            provider.polling_timestamp = None
            provider.save()
        with patch.object(AWSOrgUnitCrawler, "crawl_account_hierarchy") as mock_crawler:
            mock_crawler.return_value = True
            with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
                tasks.crawl_account_hierarchy()
                expected_log_msg = f"Account hierarchy crawler found {len(polling_accounts)} accounts to scan"
        self.assertIn(expected_log_msg, captured_logs.output[0])
        mock_crawler.assert_called()

    @patch("masu.celery.tasks.NotificationService")
    def test_cost_model_status_check_with_provider_uuid(self, mock_notification):
        """Test that only accounts associated with the provider_uuid are polled."""
        mock_notification.cost_model_notification.return_value = True
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.check_cost_model_status(self.ocp_test_provider_uuid)
            expected_log_msg = "Cost model status check found 1 providers to scan"
            self.assertIn(expected_log_msg, captured_logs.output[0])
        mock_notification.assert_not_called()  # the test-ocp-source has a cost model; this mock should not be called

    def test_cost_model_status_check_with_incompatible_provider_uuid(self):
        """Test that only accounts associated with the provider_uuid are polled."""
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.check_cost_model_status(self.gcp_test_provider_uuid)
            expected_log_msg = f"Source {self.gcp_test_provider_uuid} is not an openshift source."

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @patch("masu.celery.tasks.NotificationService")
    def test_cost_model_status_check_without_provider_uuid(self, mock_notification):
        """Test that all polling accounts are used when no provider_uuid is provided."""
        mock_notification.cost_model_notification.return_value = True
        baker.make("Provider", type=Provider.PROVIDER_OCP, customer=self.customer)
        providers = Provider.objects.filter(infrastructure_id__isnull=True, type=Provider.PROVIDER_OCP).all()
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.check_cost_model_status()
            expected_log_msg = f"Cost model status check found {len(providers)} providers to scan"
            self.assertIn(expected_log_msg, captured_logs.output[0])
        mock_notification.assert_called()  # the baked ocp source does not have cost model; this mock should be called

    def test_stale_ocp_source_check_with_provider_uuid(self):
        """Test that only accounts associated with the provider_uuid are polled."""
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.check_for_stale_ocp_source(self.ocp_test_provider_uuid)
            expected_log_msg = "Openshift stale cluster check found 1 clusters to scan"
            self.assertIn(expected_log_msg, captured_logs.output[0])

    def test_stale_ocp_source_check_without_provider_uuid(self):
        """Test that all polling accounts are used when no provider_uuid is provided."""
        manifests = ReportManifestDBAccessor().get_last_manifest_upload_datetime()
        with self.assertLogs("masu.celery.tasks", "INFO") as captured_logs:
            tasks.check_for_stale_ocp_source()
            expected_log_msg = f"Openshift stale cluster check found {len(manifests)} clusters to scan"

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @patch("masu.celery.tasks.celery_app")
    def test_collect_queue_len(self, mock_celery_app):
        """Test that the collect queue len function runs correctly."""
        mock_celery_app.pool.acquire(block=True).default_channel.client.llen.return_value = 2
        with self.assertLogs("masu.celery.tasks", "DEBUG") as captured_logs:
            print(f"\n\n{tasks.collect_queue_metrics()}\n\n")
            expected_log_msg = "Celery queue backlog info: "

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_delete_provider_async_not_found(self):
        """Test that delete_provider_async does not raise unhandled error on missing Provider."""
        provider_uuid = "00000000-0000-0000-0000-000000000001"
        with self.assertLogs("masu.celery.tasks", "WARNING") as captured_logs:
            tasks.delete_provider_async("fake name", provider_uuid, "fake_schema")
            expected_log_msg = "does not exist"

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_out_of_order_source_delete_async_not_found(self):
        """Test that out_of_order_source_delete_async does not raise unhandled error or missing Source."""
        source_id = 0
        with self.assertLogs("masu.celery.tasks", "WARNING") as captured_logs:
            tasks.out_of_order_source_delete_async(source_id)
            expected_log_msg = "does not exist"

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_missing_source_delete_async_not_found(self):
        """Test that missing_source_delete_async does not raise unhandled error on missing Source."""
        source_id = 0
        with self.assertLogs("masu.celery.tasks", "WARNING") as captured_logs:
            tasks.missing_source_delete_async(source_id)
            expected_log_msg = "does not exist"

        self.assertIn(expected_log_msg, captured_logs.output[0])

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=False)
    def test_purge_s3_files_failed_unleash(self, _):
        """Test that the scheduled task calls the orchestrator."""
        msg = tasks.purge_s3_files("/fake/path/", "act1111", "GCP", "123456")
        expected_msg = "Schema act1111 not enabled in unleash."
        self.assertEqual(msg, expected_msg)

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=True)
    def test_purge_s3_files_missing_params(self, _):
        """Test that the scheduled task calls the orchestrator."""
        with self.assertRaises(TypeError):
            tasks.purge_s3_files(None, None, None, None)

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=True)
    @patch("masu.celery.tasks.deleted_archived_with_prefix")
    @override_settings(SKIP_MINIO_DATA_DELETION=True)
    def test_purge_s3_files_skipped_minio_true(self, delete_call, *args):
        """Test that the scheduled task calls the orchestrator."""
        tasks.purge_s3_files("/fake/path/", "act1111", "GCP", "123456")
        delete_call.assert_not_called()

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=True)
    @patch("masu.celery.tasks.deleted_archived_with_prefix")
    @override_settings(SKIP_MINIO_DATA_DELETION=False)
    def test_purge_s3_files_success(self, delete_call, *args):
        """Test that the scheduled task calls the orchestrator."""
        tasks.purge_s3_files("/fake/path/", "act1111", "GCP", "123456")
        delete_call.assert_called()

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=True)
    def test_purge_manifest_success(self, _):
        """Test that the scheduled task calls the orchestrator."""
        dates = {"start_date": datetime.now().date(), "end_date": datetime.now().date()}
        with patch("masu.celery.tasks.ReportManifestDBAccessor") as mock_accessor:
            tasks.purge_manifest_records("act1111", self.gcp_provider_uuid, dates)
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            mock_accessor.assert_called()

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=False)
    def test_purge_manifest_fail(self, _):
        """Test that the scheduled task calls the orchestrator."""
        dates = {"bill_date": datetime.now().date()}
        with patch("masu.celery.tasks.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            tasks.purge_manifest_records("act1111", "123456", dates)
            mock_accessor.assert_not_called()

    @patch("masu.celery.tasks.is_purge_trino_files_enabled", return_value=True)
    def test_purge_manifest_fail_no_dates(self, _):
        """Test that the scheduled task calls the orchestrator."""
        dates = {}
        with patch("masu.celery.tasks.ReportManifestDBAccessor") as mock_accessor:
            tasks.purge_manifest_records("act1111", "123456", dates)
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            mock_accessor.assert_called_once()

    def test_purge_manifest_schema_not_in_unleash(self):
        """Test that a schema not being enabled for purging does not purge records."""
        dates = {}
        with patch("masu.celery.tasks.ReportManifestDBAccessor") as mock_accessor:
            returned_msg = tasks.purge_manifest_records("acct0000", "0000", dates)
            expected_msg = "Schema acct0000 not enabled in unleash."
            self.assertEqual(returned_msg, expected_msg)
            mock_accessor.assert_not_called()

    @patch("masu.celery.tasks.celery_app")
    def test_get_celery_queue_items(self, mock_celery_app):
        """Test that collecting tasks from the queue returns results from the expected queues."""
        queue_tasks = tasks.get_celery_queue_items()
        for queue in QUEUES:
            self.assertIn(queue, queue_tasks)

    @patch("masu.celery.tasks.celery_app")
    def test_get_celery_queue_items_single_queue(self, mock_celery_app):
        """Test that collecting tasks from a specific queue returns results from only that queue."""
        expected_queue = "summary"
        queue_tasks = tasks.get_celery_queue_items(queue_name=expected_queue)
        for queue in QUEUES:
            if queue == expected_queue:
                self.assertIn(queue, queue_tasks)
            else:
                self.assertNotIn(queue, queue_tasks)

    @patch("masu.celery.tasks.celery_app")
    def test_get_celery_queue_items_returned(self, mock_celery_app):
        """Test that the right information is returned from a specific queue."""
        mock_celery_app.pool.acquire().__enter__().default_channel.client.lrange.return_value = [
            b'{"body": "W1sib3JnMTIzNDU2NyIsICJBV1MtbG9jYWwiLCAiNjQzZjExYWYtYmIwYy00Yjg1LWIyOTEtMjNkMDQ1NGM5MTIyIiwgIjIwMjMtMDktMjkiLCAiMjAyMy0wOS0zMCJdLCB7Imludm9pY2VfbW9udGgiOiBudWxsLCAicXVldWVfbmFtZSI6ICJzdW1tYXJ5IiwgIm9jcF9vbl9jbG91ZCI6IHRydWV9LCB7ImNhbGxiYWNrcyI6IG51bGwsICJlcnJiYWNrcyI6IG51bGwsICJjaGFpbiI6IG51bGwsICJjaG9yZCI6IG51bGx9XQ==", "content-encoding": "utf-8", "content-type": "application/json", "headers": {"lang": "py", "task": "masu.processor.tasks.update_summary_tables", "id": "6cad815a-29cb-42cd-a453-f7c73467fb6c","shadow": null, "eta": null, "expires": null, "group": null, "group_index": null, "retries": 0, "timelimit": [null, null], "root_id": "6cad815a-29cb-42cd-a453-f7c73467fb6c", "parent_id": null,"argsrepr": "(\'org1234567\', \'AWS-local\', \'643f11af-bb0c-4b85-b291-23d0454c9122\', \'2023-09-29\', \'2023-09-30\')", "kwargsrepr": "{\'invoice_month\': None, \'queue_name\': \'summary\', \'ocp_on_cloud\': True}", "origin": "gen35@827332896fa1", "ignore_result": false}, "properties": {"correlation_id": "6cad815a-29cb-42cd-a453-f7c73467fb6c", "reply_to": "4c8e3925-1db1-3850-88e3-9bf2db8dd3ca", "delivery_mode": 2, "delivery_info": {"exchange": "", "routing_key": "summary"}, "priority": 0, "body_encoding": "base64", "delivery_tag": "bff35e29-d998-43cd-b0fc-109a84bdefc2"}}'  # noqa: E501
        ]
        expected_output = {
            "summary": [
                {
                    "name": "masu.processor.tasks.update_summary_tables",
                    "id": "6cad815a-29cb-42cd-a453-f7c73467fb6c",
                    "args": "('org1234567', 'AWS-local', '643f11af-bb0c-4b85-b291-23d0454c9122', '2023-09-29', '2023-09-30')",  # noqa: E501
                    "kwargs": "{'invoice_month': None, 'queue_name': 'summary', 'ocp_on_cloud': True}",
                }
            ]
        }
        expected_queue = "summary"
        queue_tasks = tasks.get_celery_queue_items(queue_name=expected_queue)
        self.assertEqual(queue_tasks, expected_output)

    @patch("masu.celery.tasks.celery_app")
    def test_get_celery_queue_no_items_returned_task_name(self, mock_celery_app):
        """Test that no items are returned when specifying a task name that is not queued."""
        mock_celery_app.pool.acquire().__enter__().default_channel.client.lrange.return_value = [
            b'{"body": "W1sib3JnMTIzNDU2NyIsICJBV1MtbG9jYWwiLCAiNjQzZjExYWYtYmIwYy00Yjg1LWIyOTEtMjNkMDQ1NGM5MTIyIiwgIjIwMjMtMDktMjkiLCAiMjAyMy0wOS0zMCJdLCB7Imludm9pY2VfbW9udGgiOiBudWxsLCAicXVldWVfbmFtZSI6ICJzdW1tYXJ5IiwgIm9jcF9vbl9jbG91ZCI6IHRydWV9LCB7ImNhbGxiYWNrcyI6IG51bGwsICJlcnJiYWNrcyI6IG51bGwsICJjaGFpbiI6IG51bGwsICJjaG9yZCI6IG51bGx9XQ==", "content-encoding": "utf-8", "content-type": "application/json", "headers": {"lang": "py", "task": "masu.processor.tasks.update_summary_tables", "id": "6cad815a-29cb-42cd-a453-f7c73467fb6c","shadow": null, "eta": null, "expires": null, "group": null, "group_index": null, "retries": 0, "timelimit": [null, null], "root_id": "6cad815a-29cb-42cd-a453-f7c73467fb6c", "parent_id": null,"argsrepr": "(\'org1234567\', \'AWS-local\', \'643f11af-bb0c-4b85-b291-23d0454c9122\', \'2023-09-29\', \'2023-09-30\')", "kwargsrepr": "{\'invoice_month\': None, \'queue_name\': \'summary\', \'ocp_on_cloud\': True}", "origin": "gen35@827332896fa1", "ignore_result": false}, "properties": {"correlation_id": "6cad815a-29cb-42cd-a453-f7c73467fb6c", "reply_to": "4c8e3925-1db1-3850-88e3-9bf2db8dd3ca", "delivery_mode": 2, "delivery_info": {"exchange": "", "routing_key": "summary"}, "priority": 0, "body_encoding": "base64", "delivery_tag": "bff35e29-d998-43cd-b0fc-109a84bdefc2"}}'  # noqa: E501
        ]
        expected_output = {"summary": []}
        expected_queue = "summary"
        queue_tasks = tasks.get_celery_queue_items(queue_name=expected_queue, task_name="not_found")
        self.assertEqual(queue_tasks, expected_output)
